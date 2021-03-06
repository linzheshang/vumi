# -*- test-case-name: vumi.tests.test_log -*-
import logging
from functools import partial

from twisted.python import log


debug = partial(log.msg, logLevel=logging.DEBUG)
info = partial(log.msg, logLevel=logging.INFO)
warning = partial(log.msg, logLevel=logging.WARNING)
error = partial(log.err, logLevel=logging.ERROR)
critical = partial(log.err, logLevel=logging.CRITICAL)

# make transition from twisted.python.log easier
msg = info
err = error


class WrappingLogger(object):
    '''A logger that will add the additional arguments that it is initialized
    with to every logging call.'''
    def __init__(self, **kwargs):
        self.debug = partial(debug, **kwargs)
        self.info = partial(info, **kwargs)
        self.warning = partial(warning, **kwargs)
        self.error = partial(error, **kwargs)
        self.critical = partial(critical, **kwargs)
        self.msg = partial(msg, **kwargs)
        self.err = partial(err, **kwargs)
