import re
from pandas import Series,DataFrame,concat
import pandas as pd
from pymongo import MongoClient
import json
import logging
from logging.config import fileConfig
import configparser

fileConfig('logger_config.ini')
logger=logging.getLogger('infoLogger')

class TransOC4J():
    def __init__(self):
        self.cfg = configparser.ConfigParser()
        self.cfg.read("config.ini")        
        cmdb_db = self.cfg.get("cmdb","db")
        cmdb_str = self.cfg.get("cmdb","conn_str")
        self.client = MongoClient(cmdb_str)
        self.db = self.client[cmdb_db]
    
    def write_to_cmdb(self,coll_name,df):
        coll = self.db[coll_name]
        result =  coll.delete_many({})
        logger.info("%s deleted %s rows" % (coll_name,str(result.deleted_count)))
        result = coll.insert_many(json.loads(df.to_json(orient='records')))
        logger.info("%s inserted %s rows" % (coll_name,str(len(result.inserted_ids))))

    def main(self):
        oc4j_coll = self.db['zabbix_oc4j']
        oc4j_df = pd.DataFrame(list(oc4j_coll.find())).fillna(value='')
        merge_oc4j_df = pd.DataFrame()
        merge_oc4j_df['merge_environment'] = oc4j_df['zabbix_environment']
        merge_oc4j_df['merge_server'] = oc4j_df['zabbix_hosts'].map(lambda x:[it.get('host') for it in x][0])
        merge_oc4j_df['merge_name'] = oc4j_df['zabbix_name'].map(lambda x:x.split()[-1])
        merge_oc4j_df['merge_domain'] = oc4j_df['zabbix_name'].map(lambda x:x.split()[-2])
        merge_oc4j_df['merge_item'] = oc4j_df['zabbix_key_'].map(lambda x:re.search(r'(?P<item>.*)\[.*',x).groupdict().get('item').replace('.','_'))
        merge_oc4j_df['merge_item_value_m'] = oc4j_df['zabbix_prevvalue'].map(lambda x:re.search(r'(?P<item_value>\d*)\w*',x    ).  groupdict().get('item_value'))
        self.write_to_cmdb(coll_name='merge_oc4j',df=merge_oc4j_df)
        self.client.close()

if __name__ == '__main__':
    oc4j = TransOC4J()
    oc4j.main()