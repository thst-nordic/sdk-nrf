


rm date.txt
git add -A && git commit -m 'GET_SET' && git push origin 
sleep 3
jcli build buran/thst/sdk-nrf/PR-39 -p RUN_TESTS=false -p RUN_BUILD=false
date >> date.txt
git add date.txt && git commit -m 'RACE: new date' && git push origin

jcli console -f buran/thst/sdk-nrf/PR-39 | tee nrf.log
jcli console -f buran/thst/sub/test-fw-nrfconnect-nrf/master | tee test_nrf.log

echo "\n\n\n\n\n\n\n\n\n"
echo "NRF: "
grep "GIT_COMMIT" nrf.log -m 1 | awk -F" " '{print $3}' | sed 's/"//' | sed 's/",//'

echo "\n\n\n"

echo "TEST_NRF: "
grep -A 2 "NRF COMMITS:" test_nrf.log 

