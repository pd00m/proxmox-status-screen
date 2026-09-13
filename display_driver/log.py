# SPDX-License-Identifier: GPL-3.0-or-later
#
# Logger shim for the vendored display driver.
#
# The driver modules were copied from turing-smart-screen-python, where they imported
# `library.log.logger`. To keep the vendored driver independent from this application's
# logging configuration, we only expose a named logger here: handlers/levels are set up by
# `proxmox_status_screen.log`.

import logging

logger = logging.getLogger("proxmox-status-screen")
