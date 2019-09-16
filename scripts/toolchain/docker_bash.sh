#!/usr/bin/env sh

NAME=ncs

SCRIPTPATH=`dirname $(readlink -f $0)`
cd $SCRIPTPATH/..   # get out of utils directory

if [ ! "$(docker ps -q -f name=$NAME)" ]; then
 	$SCRIPTPATH/docker_start.sh
fi

docker exec -it $NAME bash
