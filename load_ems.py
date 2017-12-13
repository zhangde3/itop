from sqlalchemy import create_engine
import re
from pandas import Series, DataFrame, concat
import pandas as pd
from pymongo import MongoClient
import subprocess as t
import logging
from logging.config import fileConfig
import configparser

fileConfig('logger_config.ini')
logger=logging.getLogger('infoLogger')

class LoadEMS():

    def __init__(self):
        self.cfg = configparser.ConfigParser()
        self.cfg.read("config.ini")        
        cmdb_db = self.cfg.get("cmdb","db")
        cmdb_str = self.cfg.get("cmdb","conn_str")
        self.client = MongoClient(cmdb_str)
        self.db = self.client[cmdb_db]
        
        self.engine = create_engine(
            "mysql+pymysql://root:Password1@127.0.0.1:3306/itop?charset=utf8", encoding="utf-8", echo=False)

    def load_to_itopdb(self, df, source_table_name):
        self.engine.execute("delete from %s" % source_table_name)
        df.to_sql(source_table_name, con=self.engine,
                  if_exists='append', index=False)

    def apply_by_php(self, source_table_name):
        source_table_id = source_table_name.split('_').pop()
        php_cmd = "php -q /itop_data/http_dir/itop/synchro/synchro_exec.php --auth_user=%s --auth_pwd=%s --data_sources=%s" % (
            'admin', 'Password1', source_table_id)
        output = t.getoutput(php_cmd)
        logger.info(output + "\n")

    def get_id(self, table_name):
        get_id_sql = "select id,name from %s" % (table_name)
        id_df = pd.read_sql(get_id_sql, con=self.engine)
        id_df['id'] = id_df['id'].map(lambda x: str(int(x)))
        return id_df

    def get_ems_src_df(self):
        ems_coll = self.db['merge_ems']
        ems_df = pd.DataFrame(list(ems_coll.find())).assign(join_server_name=lambda x:x['merge_server'].str.upper())

        middleware_id_df = self.get_id('view_Middleware').assign(join_name=lambda x:x['name'].str.upper())[['join_name','id']]

        ems_df = pd.merge(ems_df,middleware_id_df,how='left',left_on='join_server_name',right_on='join_name').rename(columns={'id':'middleware_id'})

        prefix = 'merge_'

        col_dict = {}
        for col in ems_df.columns:
            if prefix in col:
                col_dict[col] = col.split(prefix)[1]

        ems_src_df = ems_df.rename(columns=col_dict)[['name','middleware_id','environment','port']].assign(org_id=lambda x:1).assign(primary_key=lambda x:x['name'])

        ems_src_df =ems_src_df[ems_src_df['middleware_id'].notnull()]
        
        return ems_src_df

    def main(self):
        ems_src_df = self.get_ems_src_df()
        self.load_to_itopdb(
            df=ems_src_df, source_table_name='synchro_data_emsinstance_94')
        self.apply_by_php(source_table_name='synchro_data_emsinstance_94')


if __name__ == '__main__':
    ems = LoadEMS()
    ems.main()
