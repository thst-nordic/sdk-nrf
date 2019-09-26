#!/usr/bin/env bash

SCRIPTPATH=`dirname $(readlink -f $0)`
cd $SCRIPTPATH/../../..   # get to the ZEPHYR_ROOT directory

NAME=ncs
VER=$1
if [ -z $VER ]; then
  DEFAULT_VER='latest'
  VER=$DEFAULT_VER
fi

if [ "$(docker ps -q -f name=$NAME)" ]; then
    echo 'A docker container is already running..'
    read -n1 -p "Do you want to remove the previous container? [y,n]" doit
    case $doit in
      y|Y) echo; echo yes; docker stop $NAME; docker container rm $NAME  ;;
      n|N) echo; echo no;  ;;
      *) echo dont know ;;
    esac
fi

WORKDIR=/work
if [ ! "$(docker ps -q -f name=$NAME)" ]; then
    if [ "$(docker ps -aq -f status=exited -f name=$NAME)" ]; then
        # cleanup
        docker rm $NAME
    fi
    docker run -d                                  \
          --name $NAME                             \
          -u root                                  \
          -w $WORKDIR                              \
          -v $(pwd):$WORKDIR:rw,z                  \
        itsrv80.nordicsemi.no/ncs-toolchain:$VER   \
      tail -f /dev/null
    echo 'A docker container is now running.'
fi
          # -e BASE='$NAME/ncs'                      \

echo 'To get inside:'
echo "  $ docker exec -it $NAME bash"
echo '             or'
echo '  $ ./scripts/toolchain/docker_bash'

