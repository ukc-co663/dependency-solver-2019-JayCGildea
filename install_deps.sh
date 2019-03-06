#!/bin/bash
apt-get update
apt-get --assume-yes install python3-pip 
apt install libz-dev
pip3 install pycosat
pip3 install packaging
pip3 install python-sat