from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim
import ssl
import atexit
from pprint import pprint
import json
from pymongo import MongoClient
import pdb
import time
import logging
import configparser
from dump import Dump

logging.basicConfig(
    level=logging.INFO,
    #level=logging.WARNING,
    format="[%(asctime)s] %(name)s:%(levelname)s: %(message)s",
)


class ExtractVcenter():

    def __init__(self):
        self.cfg = configparser.ConfigParser()
        self.cfg.read("config.ini")        
        cmdb_db = self.cfg.get("cmdb","db")
        cmdb_str = self.cfg.get("cmdb","conn_str")
        self.client = MongoClient(cmdb_str)
        self.db = self.client[cmdb_db]

    def get_connect(self, in_host, in_user, in_pwd, in_port):
        context = None
        if hasattr(ssl, '_create_unverified_context'):
            context = ssl._create_unverified_context()
        connect = SmartConnect(host=in_host, user=in_user,
                               pwd=in_pwd, port=in_port, sslContext=context)
        if not connect:
            print("Could not connect to the specified host using specified "
                  "username and password")
            raise IOError
        else:
            # print("connected")
            self.sync_time = time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(time.time()))
            self.env='NON-PROD' if 'PP' in in_host.upper() else 'PROD'
            return connect
        atexit.register(Disconnect, connect)

    def get_data_center_list(self, connect):
        content = connect.RetrieveContent()
        dc_list = [dc for dc in content.rootFolder.childEntity]
        return dc_list

    def get_server_list(self, dc):
        server_list = []
        for cluster in dc.hostFolder.childEntity:
            for host in cluster.host:
                if host.runtime.powerState == 'poweredOff':
                    continue
                server = {}
                server['vc_power_status'] = host.runtime.powerState
                server['vc_name'] = host.name
                server['vc_brand_name'] = host.summary.hardware.vendor.upper().split(' INC.')[0]
                server['vc_model_name'] = ' '.join([server['vc_brand_name'],host.summary.hardware.model])
                server['vc_memory_size'] = str(round(host.summary.hardware.memorySize/1024/1024/1024))
                server['vc_cpu_type'] = host.summary.hardware.cpuModel
                server['vc_cpu_num'] = host.summary.hardware.numCpuPkgs
                server['vc_cpu_core'] = str(round(host.summary.hardware.numCpuCores))
                server['vc_cpu_thread'] = str(round(host.summary.hardware.numCpuThreads))
                server['vc_cpu_speedGHz'] = server['vc_cpu_type'].split().pop()
                server['vc_ip'] = host.config.network.vnic[0].spec.ip.ipAddress
                server['vc_pool'] = "ESX Server Pool"
                server['vc_os_family'] = host.summary.config.product.name
                server['vc_os_version'] = ' '.join([server['vc_os_family'],host.config.product.version])
                server['vc_fiber_hba_device'] = ",".join([ hba.device for hba in \
                host.config.storageDevice.hostBusAdapter if isinstance(hba,vim.host.FibreChannelHba)])
                server['vc_fiber_hba_num'] = str(round(len([ hba for hba in \
                                            host.config.storageDevice.hostBusAdapter if isinstance(hba,vim.host.FibreChannelHba)])))
                server['vc_pci_hba_num'] = str(round(len([ hba for hba in \
                                            host.config.storageDevice.hostBusAdapter if isinstance(hba,vim.host.ParallelScsiHba)])))
                server['vc_pci_hba_device'] = ",".join([ hba.device for hba in \
                host.config.storageDevice.hostBusAdapter if isinstance(hba,vim.host.ParallelScsiHba)])
                server['vc_env'] = self.env
                server['vc_sync_time'] = self.sync_time
                server_list.append(server)
        return server_list

    def get_vm(self, dc, vcenter_obj):
        vm = {}
        vm['vc_name'] = vcenter_obj.name
        vm['vc_connect_status'] = vcenter_obj.summary.runtime.connectionState
        vm['vc_power_status'] = vcenter_obj.summary.runtime.powerState
        vm['vc_vm_path'] = vcenter_obj.summary.config.vmPathName
        vm['vc_server_name'] = vcenter_obj.summary.runtime.host.name
        vm['vc_memory_size'] = str(round(vcenter_obj.summary.config.memorySizeMB / 1024)) if vcenter_obj.summary.config.memorySizeMB else '0'
        vm['vc_cpu_num'] = vcenter_obj.summary.config.numCpu
        vm['vc_ethernetcard_num'] = vcenter_obj.summary.config.numEthernetCards
        vm['vc_virtualdisk_num'] = vcenter_obj.summary.config.numVirtualDisks
        vm['vc_server_fullname'] = vcenter_obj.summary.config.guestFullName
        vm['vc_ip'] = vcenter_obj.summary.guest.ipAddress
        vm['vc_vm_os_family'] = vcenter_obj.guest.guestFamily
        vm['vc_vm_os_version'] = vcenter_obj.summary.config.guestFullName
        vm['vc_env'] = self.env
        vm['vc_sync_time'] = self.sync_time
        vm['vc_annotation'] = vcenter_obj.summary.config.annotation if vcenter_obj.summary.config.annotation else ''
        return vm

    def get_vm_list(self, dc):
        vm_list = []
        for v in dc.vmFolder.childEntity:
            if hasattr(v, 'childEntity'):
                for vv in v.childEntity:
                    # if vv.summary.runtime.powerState == 'poweredOff':
                    #     continue
                    vm = self.get_vm(dc, vv)
                    vm_list.append(vm)
            else:
                # if v.summary.runtime.powerState == 'poweredOff':
                #     continue
                vm = self.get_vm(dc, v)
                vm_list.append(vm)
        return vm_list

    def get_ds_list(self, dc):
        datastore_list = []
        for v_ds in dc.datastore:
            ds = {}
            ds['vc_name'] = v_ds.name
            ds['vc_url'] = v_ds.summary.url
            ds['vc_capacity'] = v_ds.summary.capacity
            ds['vc_freespace'] = v_ds.summary.freeSpace
            ds['vc_type'] = v_ds.summary.type
            ds['vc_uncommitted'] = v_ds.summary.uncommitted
            ds['vc_vmfs_version'] = v_ds.info.vmfs.version
            ds['vc_vms'] = [vm.name for vm in v_ds.vm]
            ds['vc_hosts'] = [host.key.name for host in v_ds.host]
            ds['vc_env'] = self.env
            datastore_list.append(ds)
        return datastore_list

    def get_license_list(self,connect):
        content = connect.RetrieveContent()
        
        license_list = []
        for it in content.licenseManager.licenses:
            if it.name != 'Product Evaluation':
                license = {}
                license['costUnit'] = it.costUnit
                license['editionKey'] = it.editionKey
                license['labels'] = it.labels
                license['licenseKey'] = it.licenseKey
                license['name'] = it.name
                license['total'] = it.total
                license['used'] = it.used
                if 'PP' in self.in_host.upper():
                    license['environment'] = 'NON-PROD'
                else:
                    license['environment'] = 'PROD'
                license_list.append(license)
        return license_list

    def load_jsonlist_to_mongodb(self, coll_name, json_list):
        if json_list:
            coll = self.db[coll_name]
            # result = coll.delete_many({})
            # print("%s deleted %s" % (coll_name, str(result.deleted_count)))
            result = coll.insert_many(json_list)
            logging.info("%s inserted %s" % (coll_name, str(len(result.inserted_ids))))

    def extract_load(self,in_host,in_user,in_pwd,in_port):
        connect = self.get_connect(in_host, in_user, in_pwd, in_port)
        dc_list = self.get_data_center_list(connect)

        logging.info('processing %s' % in_host)
        for dc in dc_list:
            server_json_list = self.get_server_list(dc)
            self.load_jsonlist_to_mongodb(coll_name='vcenter_server', json_list=server_json_list)

            vm_json_list = self.get_vm_list(dc)
            self.load_jsonlist_to_mongodb(coll_name='vcenter_virtualmachine', json_list=vm_json_list)

            ds_json_list = self.get_ds_list(dc)
            self.load_jsonlist_to_mongodb(coll_name='vcenter_logicalvolume', json_list=ds_json_list)

            # license_list = self.get_license_list(connect)
            # self.load_jsonlist_to_mongodb(coll_name='vcenter06_vmware_license', json_list=license_list)

    def main(self):
        vc02_section = "vc02"
        vc02_host = self.cfg.get(vc02_section,"host")
        vc02_user = self.cfg.get(vc02_section,"user")
        vc02_passwd = self.cfg.get(vc02_section,"passwd")
        vc02_port = self.cfg.getint(vc02_section,"port")
        self.extract_load(in_host=vc02_host,in_user=vc02_user,in_pwd=vc02_passwd,in_port=vc02_port)

        vc06_section = "vc06"
        vc06_host = self.cfg.get(vc06_section,"host")
        vc06_user = self.cfg.get(vc06_section,"user")
        vc06_passwd = self.cfg.get(vc06_section,"passwd")
        vc06_port = self.cfg.getint(vc06_section,"port")
        self.extract_load(in_host=vc06_host,in_user=vc06_user,in_pwd=vc06_passwd,in_port=vc06_port)

        ppvc06_section = "ppvc06"
        ppvc06_host = self.cfg.get(ppvc06_section,"host")
        ppvc06_user = self.cfg.get(ppvc06_section,"user")
        ppvc06_passwd = self.cfg.get(ppvc06_section,"passwd")
        ppvc06_port = self.cfg.getint(ppvc06_section,"port")
        self.extract_load(in_host=ppvc06_host,in_user=ppvc06_user,in_pwd=ppvc06_passwd,in_port=ppvc06_port)


if __name__ == '__main__':
    vc = ExtractVcenter()
    vc.main()
