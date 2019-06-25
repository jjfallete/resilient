# This Carbon Black package initializer sets up host locking and removes old host lock files.
# File: __init__.py
# Date: 04/28/2019 - Modified: 06/25/2019
# Author: Jared F

import os
import logging
log = logging.getLogger(__name__)  # Establish logging

if os.path.exists('/home/integrations/.resilient/cb_host_locks'):
	lock_file_list = [f for f in os.listdir('/home/integrations/.resilient/cb_host_locks') if f.endswith(".lock")]
	for lock_file in lock_file_list:
		os.remove(os.path.join('/home/integrations/.resilient/cb_host_locks', lock_file))
		log.info("[INFO] carbon_black's __init__ script has removed: " + str(lock_file))

else:
	os.makedirs('/home/integrations/.resilient/cb_host_locks')
