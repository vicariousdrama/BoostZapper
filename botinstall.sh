#!/usr/bin/env bash

# Script config for development/testing - not user config options
GITCLONEREPO="https://github.com/vicariousdrama/BoostZapper.git"
GITCLONEBRANCH="main"

# Tools
echo "================================================"
echo "TOOLS:"
echo "updating system..."
apt-get update          # without this, a few packages may fail
echo "ensuring dependent packages are installed..."
apt-get -y install \
    git \
    python3 \
    python3-venv 

# Create Boost Zapper user
echo "================================================"
echo "CREATING BOOSTZAPPER USER"
CREATED_USER=0
if id boostzapper &>/dev/null; then
  echo "BoostZapper user already exists"
else
  echo "Creating BoostZapper user"
  DRIVECOUNT=$(df -t ext4 | grep / | awk '{print $6}' | sort | wc -l)
  ISMMC=$(findmnt -n -o SOURCE --target /home | grep "mmcblk" | wc -l)
  if [ $DRIVECOUNT -gt 1 ] && [ $ISMMC -gt 0 ]; then
    EXT_DRIVE_MOUNT=$(df -t ext4 | grep / | awk '{print $6}' | sort | sed -n 2p)
  fi
  if [ -z ${EXT_DRIVE_MOUNT+x} ]; then
    echo "- creating user with home in default location"
    BOOSTZAPPER_HOME=/home/boostzapper
    adduser --gecos "" --disabled-password boostzapper
  else
    echo "- creating user with home on external drive mount"
    BOOSTZAPPER_HOME=${EXT_DRIVE_MOUNT}/boostzapper
    adduser --home ${BOOSTZAPPER_HOME} --gecos "" --disabled-password boostzapper
    ln -s ${BOOSTZAPPER_HOME} /home/boostzapper
    chown -R boostzapper:boostzapper /home/boostzapper
  fi
  CREATED_USER=1
fi

# Clone repository into boostzapper user space
echo "================================================"
echo "GIT REPOSITORY:"
CLONED_REPO=0
GITPULLRESULT=""
if [ ! -d "/home/boostzapper/BoostZapper" ]; then
  echo "cloning BoostZapper..."
  sudo -u boostzapper git clone --single-branch --branch $GITCLONEBRANCH $GITCLONEREPO /home/boostzapper/BoostZapper
  chown -R boostzapper:boostzapper /home/boostzapper/BoostZapper
  CLONED_REPO=1
else
  echo "detected folder at /home/boostzapper/BoostZapper"
  echo "fetching and pulling latest changes..."
  GITPULLRESULT=$(sudo -u boostzapper bash -c "cd /home/boostzapper/BoostZapper && git pull")
fi

# Create python virtual environment in boostzapper user space
echo "================================================"
echo "PYTHON ENVIRONMENT:"
CREATED_PYENV=0
if [ ! -d "/home/boostzapper/.pyenv/boostzapper" ]; then
  echo "creating python virtual environment"
  sudo -u boostzapper python3 -m venv /home/boostzapper/.pyenv/boostzapper
  CREATED_PYENV=1
else
  echo "detected existing python virtual environment"
fi
# ensure python modules we depend on are present in the virtual environment
echo "ensuring required modules..."
#sudo -u boostzapper -s source /home/boostzapper/.pyenv/boostzapper/bin/activate && /home/boostzapper/.pyenv/boostzapper/bin/python3 -m pip install --upgrade \
#    bech32 boto3 requests
#sudo -u boostzapper -s source /home/boostzapper/.pyenv/boostzapper/bin/activate && /home/boostzapper/.pyenv/boostzapper/bin/python3 -m pip install --upgrade \
#    nostr@git+https://github.com/vicariousdrama/python-nostr.git
sudo -u boostzapper bash -c "source /home/boostzapper/.pyenv/boostzapper/bin/activate && /home/boostzapper/.pyenv/boostzapper/bin/python3 -m pip install --upgrade bech32 boto3 requests"
sudo -u boostzapper bash -c "source /home/boostzapper/.pyenv/boostzapper/bin/activate && /home/boostzapper/.pyenv/boostzapper/bin/python3 -m pip install --upgrade nostr@git+https://github.com/vicariousdrama/python-nostr.git"

# Services
echo "================================================"
echo "SERVICES:"
echo "installing..."
cp /home/boostzapper/BoostZapper/boostzapper-bot.service /etc/systemd/system/
systemctl enable boostzapper-bot.service
# systemctl start boostzapper-bot.service