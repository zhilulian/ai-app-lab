#!/bin/bash

set -ex
cd `dirname $0`

export RUNTIME_LOGDIR=/opt/tiger/toutiao/log
export PYTHONPATH=./site-packages

exec python3 main.py
