#!/bin/bash

set -eu

source /etc/os-release

LIBXLST=libxslt-dev
SOUNDFONT=musescore-soundfont-gm
LIBPNG_DEV=libpng-dev
LIBMYSQL_DEV=libmariadbclient-dev
LIBGLES="libgles1-mesa-dev libgles2-mesa-dev"
TURBOGEARS=python-turbogears
SOUNDFONT=musescore-soundfont-gm

if [ $ID = raspbian ]; then
    # temporary hack for unreleased debian version (has no version id)
    if [ ! $VERSION_ID ]; then
        VERSION_ID=10
    fi
    if [ $VERSION_ID -eq 8 ]; then
        LIBPNG_DEV=libpng12-dev
        LIBMYSQL_DEV=libmysqlclient-dev
        POSTGRES_SERVER_DEV=postgresql-server-dev-9.4
    elif [ $VERSION_ID -eq 9 ]; then
        POSTGRES_SERVER_DEV=postgresql-server-dev-9.6
    elif [ $VERSION_ID -eq 10 ]; then
        POSTGRES_SERVER_DEV=postgresql-server-dev-11
        LIBGLES=libgles2-mesa-dev
        TURBOGEARS=python-turbogears2
        SOUNDFONT=timgm6mb-soundfont
    fi
elif [ $ID = ubuntu ]; then
    LIBXLST=libxslt1-dev
    TURBOGEARS=python-turbogears2
    SOUNDFONT=timgm6mb-soundfont
    LIBGLES=libgles2-mesa-dev
    POSTGRES_SERVER_DEV=postgresql-server-dev-10
fi

apt update
apt -y upgrade
apt -y install vim ssh-import-id tree byobu htop pkg-config gfortran cmake \
	qt4-qmake qt5-qmake python-dev python3-dev \
	$LIBPNG_DEV $LIBMYSQL_DEV $LIBGLES $LIBXLST $TURBOGEARS $SOUNDFONT \
	$POSTGRES_SERVER_DEV zlib1g-dev libpq-dev libffi-dev libxml2-dev \
	libhdf5-dev	libldap2-dev libjpeg-dev libbluetooth-dev libusb-dev \
	libhidapi-dev libfreetype6-dev liblcms2-dev libzbar-dev libbz2-dev \
	libblas-dev	liblapack-dev liblapacke-dev libcurl4-openssl-dev libgmp-dev \
	libgstreamer1.0-dev libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev \
	libsdl2-ttf-dev libssl-dev libsasl2-dev libldap2-dev libavcodec-dev \
	libavformat-dev libswscale-dev libv4l-dev libxvidcore-dev libx264-dev \
	libgtk2.0-dev libgtk-3-dev libatlas-base-dev python-numpy python3-numpy \
	python-scipy python3-scipy python-matplotlib python3-matplotlib \
	python-pandas python3-pandas cython cython3 python-yaml python3-yaml \
    python-lxml python3-lxml python-cffi python3-cffi python-bs4 python3-bs4 \
    python-click python3-click python-sqlalchemy python3-sqlalchemy \
    python-pil python3-pil python-pymongo python3-pymongo python-django \
	python3-django python-flask python3-flask python-cherrypy \
    python3-cherrypy3 python-tornado python3-tornado python-pip python3-pip \
    python-redis python3-redis python-dateutil python3-dateutil \
	python-dnspython python3-dnspython python-sphinx python3-sphinx \ 
	python-boto python3-boto python-gi python3-gi python-gi-cairo python3-zmq \
	python3-gi-cairo python-cairocffi python3-cairocffi ipython ipython3 git \
	libsdl-image1.2-dev libsdl-mixer1.2-dev libsdl-ttf2.0-dev libsdl1.2-dev \
    libportmidi-dev libtiff5-dev libx11-6 libx11-dev xfonts-base \
	xfonts-100dpi xfonts-75dpi xfonts-cyrillic fluid-soundfont-gm \
	libsystemd-dev libusb-1.0-0-dev libudev-dev libopus-dev libvpx-dev

pip3 install setuptools --upgrade
pip3 install pip --upgrade
hash -r

pip3 install pypandoc versioneer kervi scikit-build \
    --extra-index-url https://www.piwheels.org/simple

getent passwd piwheels && userdel -fr piwheels
getent group piwheels || groupadd piwheels
getent passwd piwheels || useradd -g piwheels -m -s /bin/bash piwheels
passwd -d piwheels

if [ -d piwheels ]; then
    cd piwheels
    git pull
    pip uninstall -y piwheels
else
    git clone https://github.com/bennuttall/piwheels
    cd piwheels
fi

cp piwheels-slave.service /etc/systemd/system/
systemctl enable piwheels-slave.service
pip3 install .

if ! grep swapfile /etc/rc.local >/dev/null; then
    dd if=/dev/zero of=/swapfile bs=1M count=1024
    chmod 0600 /swapfile
    sed -i -e '$i\
chmod 0600 /swapfile\
losetup /dev/loop0 /swapfile\
mkswap /dev/loop0\
swapon /dev/loop0\
' /etc/rc.local
fi

rm -f /etc/pip.conf
