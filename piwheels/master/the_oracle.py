# The piwheels project
#   Copyright (c) 2017 Ben Nuttall <https://github.com/bennuttall>
#   Copyright (c) 2017 Dave Jones <dave@waveform.org.uk>
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#     * Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#     * Neither the name of the copyright holder nor the
#       names of its contributors may be used to endorse or promote products
#       derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

"""
Defines :class:`TheOracle` task and the :class:`DbClient` RPC class for talking
to it.

.. autoclass:: TheOracle
    :members:

.. autoclass:: DbClient
    :members:
"""

import pickle
from collections import namedtuple

import zmq
import zmq.error

from .. import const
from .tasks import Task
from .db import Database


class TheOracle(Task):
    """
    This task provides an RPC-like interface to the database; it handles
    requests such as registering a new package, version, or build, and
    answering queries about the hashes of files. The primary clients of this
    class are :class:`~.slave_driver.SlaveDriver`,
    :class:`~.index_scribe.IndexScribe`, and :class:`~.cloud_gazer.CloudGazer`.

    Note that because database requests are notoriously variable in length the
    client RPC class (:class:`DbClient`) doesn't *directly* talk to
    :class:`TheOracle`. Rather, multiple instances of :class:`TheOracle` are
    spawned and :class:`~.seraph.Seraph` sits in front of these acting as a
    simple load-sharing router for the RPC clients.
    """
    name = 'master.the_oracle'
    instance = 0

    def __init__(self, config):
        TheOracle.instance += 1
        self.name = '%s_%d' % (TheOracle.name, TheOracle.instance)
        super().__init__(config)
        self.db = Database(config.dsn)
        db_queue = self.ctx.socket(zmq.REQ)
        db_queue.hwm = 10
        db_queue.connect(const.ORACLE_QUEUE)
        self.register(db_queue, self.handle_db_request)
        db_queue.send(b'READY')

    def handle_db_request(self, queue):
        """
        Handle incoming requests from :class:`DbClient` instances.
        """
        address, empty, msg = queue.recv_multipart()
        msg, *args = pickle.loads(msg)
        try:
            handler = {
                'ALLPKGS': self.do_allpkgs,
                'ALLVERS': self.do_allvers,
                'NEWPKG': self.do_newpkg,
                'NEWVER': self.do_newver,
                'LOGDOWNLOAD': self.do_logdownload,
                'LOGBUILD': self.do_logbuild,
                'PKGFILES': self.do_pkgfiles,
                'PKGEXISTS': self.do_pkgexists,
                'GETABIS': self.do_getabis,
                'GETPYPI': self.do_getpypi,
                'SETPYPI': self.do_setpypi,
                'GETSTATS': self.do_getstats,
            }[msg]
            result = handler(*args)
        except Exception as exc:
            self.logger.error('Error handling db request: %s', msg)
            # REP *must* send a reply even when stuff goes wrong
            # otherwise the send/recv cycle that REQ/REP depends
            # upon breaks
            queue.send_multipart([address, empty,
                                  pickle.dumps(['ERR', str(exc)])])
        else:
            queue.send_multipart([address, empty,
                                  pickle.dumps(['OK', result])])

    def do_allpkgs(self):
        """
        Handler for "ALLPKGS" message, sent by :class:`DbClient` to request the
        set of all packages define known to the database.
        """
        return self.db.get_all_packages()

    def do_allvers(self):
        """
        Handler for "ALLVERS" message, sent by :class:`DbClient` to request the
        set of all (package, version) tuples known to the database.
        """
        return self.db.get_all_package_versions()

    def do_newpkg(self, package):
        """
        Handler for "NEWPKG" message, sent by :class:`DbClient` to register a
        new package.

        :param str package:
            The name of the new package.
        """
        return self.db.add_new_package(package)

    def do_newver(self, package, version):
        """
        Handler for "NEWVER" message, sent by :class:`DbClient` to register a
        new (package, version) tuple.

        :param str package:
            The name of the package with a new version.
        :param str version:
            The new version of the package.
        """
        return self.db.add_new_package_version(package, version)

    def do_logdownload(self, download):
        """
        Handler for "LOGDOWNLOAD" message, sent by :class:`DbClient` to
        register a new download.

        :param DownloadState download:
            The download to add to the database.
        """
        return self.db.log_download(download)

    def do_logbuild(self, build):
        """
        Handler for "LOGBUILD" message, sent by :class:`DbClient` to register a
        new build result.

        :param BuildState build:
            The build to add to the database.

        :returns int:
            The id of the build generated by the database.
        """
        self.db.log_build(build)
        return build.build_id

    def do_pkgfiles(self, package):
        """
        Handler for "PKGFILES" message, sent by :class:`DbClient` to request
        details of all wheels assocated with *package*.

        :param str package:
            The name of the package to retrieve file details for.
        """
        files = self.db.get_package_files(package)
        return list(files)

    def do_pkgexists(self, package, version):
        """
        Handler for "PKGEXISTS" message, sent by :class:`DbClient` to request
        whether or not the specified *version* of *package* exists.

        :param str package:
            The name of the package to check.

        :param str version:
            The version of the package to check.
        """
        return self.db.test_package_version(package, version)

    def do_getabis(self):
        """
        Handler for "GETABIS" message, sent by :class:`DbClient` to request the
        list of all ABIs to build for.
        """
        return self.db.get_build_abis()

    def do_getpypi(self):
        """
        Handler for "GETPYPI" message, sent by :class:`DbClient` to request the
        record of the last serial number from the PyPI changelog.
        """
        return self.db.get_pypi_serial()

    def do_setpypi(self, serial):
        """
        Handler for "SETPYPI" message, sent by :class:`DbClient` to update the
        last seen serial number from the PyPI changelog.
        """
        self.db.set_pypi_serial(serial)

    def do_getstats(self):
        """
        Handler for "GETSTATS" message, sent by :class:`DbClient` to request
        the latest database statistics, returned as a list of (field, value)
        tuples.
        """
        return self.db.get_statistics().items()


class DbClient:
    """
    RPC client class for talking to :class:`TheOracle`.
    """
    stats_type = None

    def __init__(self, config):
        self.ctx = zmq.Context.instance()
        self.db_queue = self.ctx.socket(zmq.REQ)
        self.db_queue.hwm = 1
        self.db_queue.connect(config.db_queue)

    def _execute(self, msg):
        # If sending blocks this either means we're shutting down, or
        # something's gone horribly wrong (either way, raising EAGAIN is fine)
        self.db_queue.send_pyobj(msg, flags=zmq.NOBLOCK)
        status, result = self.db_queue.recv_pyobj()
        if status == 'OK':
            if result is not None:
                return result
        else:
            raise IOError(result)

    def get_all_packages(self):
        """
        See :meth:`TheOracle.do_allpkgs`.
        """
        return self._execute(['ALLPKGS'])

    def get_all_package_versions(self):
        """
        See :meth:`TheOracle.do_allvers`.
        """
        # Repackage [p, v] as (p, v)
        return self._execute(['ALLVERS'])

    def add_new_package(self, package):
        """
        See :meth:`TheOracle.do_newpkg`.
        """
        return self._execute(['NEWPKG', package])

    def add_new_package_version(self, package, version):
        """
        See :meth:`TheOracle.do_newver`.
        """
        return self._execute(['NEWVER', package, version])

    def test_package_version(self, package, version):
        """
        See :meth:`TheOracle.do_pkgexists`.
        """
        return self._execute(['PKGEXISTS', package, version])

    def log_download(self, download):
        """
        See :meth:`TheOracle.do_logdownload`.
        """
        return self._execute(['LOGDOWNLOAD', download])

    def log_build(self, build):
        """
        See :meth:`TheOracle.do_logbuild`.
        """
        build_id = self._execute(['LOGBUILD', build])
        build.logged(build_id)

    def get_package_files(self, package):
        """
        See :meth:`TheOracle.do_pkgfiles`.
        """
        return self._execute(['PKGFILES', package])

    def get_build_abis(self):
        """
        See :meth:`TheOracle.do_getabis`.
        """
        return self._execute(['GETABIS'])

    def get_pypi_serial(self):
        """
        See :meth:`TheOracle.do_getpypi`.
        """
        return self._execute(['GETPYPI'])

    def set_pypi_serial(self, serial):
        """
        See :meth:`TheOracle.do_setpypi`.
        """
        self._execute(['SETPYPI', serial])

    def get_statistics(self):
        """
        See :meth:`TheOracle.do_getstats`.
        """
        rec = self._execute(['GETSTATS'])
        if DbClient.stats_type is None:
            DbClient.stats_type = namedtuple('Statistics',
                                             tuple(k for k, v in rec))
        return DbClient.stats_type(**{k: v for k, v in rec})
