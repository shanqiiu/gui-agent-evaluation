#!/bin/bash
echo "buildVersion=${Release_Model}">buildInfo.properties
echo ${WORKSPACE}

echo "打包服务"
tar -zcvf ../TestOracleCheck.tar.gz ./ && mv ../TestOracleCheck.tar.gz ./
