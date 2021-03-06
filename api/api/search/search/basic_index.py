#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    Search
    ~~~~~

    copyright: (c) 2014 by Halfmoon Labs, Inc.
    copyright: (c) 2015 by Blockstack.org

This file is part of Search.

    Search is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    Search is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with Search. If not, see <http://www.gnu.org/licenses/>.
"""

import sys
import json
import requests

from pymongo import MongoClient

from .utils import validUsername
from .utils import get_json, config_log

from .config import RESOLVER_URL, ALL_USERS_ENDPOINT
from .config import BLOCKCHAIN_STATE_FILE, DHT_STATE_FILE

from .db import namespace, profile_data
from .db import search_profiles
from .db import people_cache, twitter_cache, username_cache

""" create the basic index
"""

log = config_log(__name__)


def get_namespace_from_resolver(url=RESOLVER_URL, endpoint=ALL_USERS_ENDPOINT):

    full_url = url + endpoint

    headers = {'Content-type': 'application/json'}

    r = requests.get(full_url, headers=headers)

    return r.json()['results']


def fetch_dht_state_from_file():
    """ takes dht state from file and saves in profile_data DB
    """

    dht_file = open(DHT_STATE_FILE, 'r')

    dht_state = dht_file.read()
    dht_state = json.loads(dht_state)

    counter = 0

    log.debug("-" * 5)
    log.debug("Fetching DHT state from file")

    for entry in dht_state:

        new_entry = {}
        new_entry['key'] = entry['key']
        new_entry['value'] = entry['value']

        profile_data.save(new_entry)

        counter += 1

        if counter % 1000 == 0:
            log.debug("Processed entries: %s" % counter)

    dht_file.close()

    profile_data.ensure_index('key')

    return


def fetch_namespace_from_file():

    blockchain_file = open(BLOCKCHAIN_STATE_FILE, 'r')

    blockchain_state = blockchain_file.read()
    blockchain_state = json.loads(blockchain_state)

    counter = 0

    log.debug("-" * 5)
    log.debug("Fetching namespace from file")

    for entry in blockchain_state:

        new_entry = {}

        username = entry['fqu'].rstrip('id')
        username = username.rstrip('.')

        key = entry['value_hash']

        check_entry = profile_data.find_one({"key": key})

        if check_entry is None:

            # data not in DHT, skip
            continue

        new_entry['username'] = username
        new_entry['profile'] = check_entry['value']
        namespace.save(new_entry)
        counter += 1

        if counter % 1000 == 0:
            log.debug("Processed entries: %s" % counter)

    blockchain_file.close()
    return


def flush_db():

    client = MongoClient()

    # delete any old cache/index
    client.drop_database('search_db')
    client.drop_database('search_cache')

    log.debug("Flushed DB")


def optimize_db():

    people_cache.ensure_index('name')
    twitter_cache.ensure_index('twitter_handle')
    username_cache.ensure_index('username')

    search_profiles.ensure_index('name')
    search_profiles.ensure_index('twitter_handle')
    search_profiles.ensure_index('username')

    log.debug("Optimized DB")


def create_search_index():
    """ takes people names from blockchain and writes deduped names in a 'cache'
    """

    # create people name cache
    counter = 0

    people_names = []
    twitter_handles = []
    usernames = []

    log.debug("-" * 5)
    log.debug("Creating search index")

    for user in namespace.find():

        # the profile/info to be inserted
        search_profile = {}

        counter += 1

        if(counter % 1000 == 0):
            log.debug("Processed entries: %s" % counter)

        if validUsername(user['username']):
            pass
        else:
            # print "ignoring: " + user['username']
            continue

        profile = get_json(user['profile'])

        if 'name' in profile:

            try:
                name = profile['name']
            except:
                continue

            try:
                name = name['formatted'].lower()
            except:
                name = name.lower()

            people_names.append(name)
            search_profile['name'] = name

        else:
            search_profile['name'] = None

        if 'twitter' in profile:
            twitter_handle = profile['twitter']

            try:
                twitter_handle = twitter_handle['username'].lower()
            except:
                try:
                    twitter_handle = profile['twitter'].lower()
                except:
                    continue

            twitter_handles.append(twitter_handle)
            search_profile['twitter_handle'] = twitter_handle

        else:
            search_profile['twitter_handle'] = None

        search_profile['username'] = user['username']
        usernames.append(user['username'])

        search_profile['profile'] = profile
        search_profiles.save(search_profile)

    # dedup names
    people_names = list(set(people_names))
    people_names = {'name': people_names}

    twitter_handles = list(set(twitter_handles))
    twitter_handles = {'twitter_handle': twitter_handles}

    usernames = list(set(usernames))
    usernames = {'username': usernames}

    # save final dedup results to mongodb (using it as a cache)
    people_cache.save(people_names)
    twitter_cache.save(twitter_handles)
    username_cache.save(usernames)

    optimize_db()

    log.debug('Created name/twitter/username search index')


if __name__ == "__main__":

    if(len(sys.argv) < 2):
        print "Usage error"
        exit(0)

    option = sys.argv[1]

    if(option == '--flush'):
        # Step 0
        flush_db()

    elif(option == '--create_namespace'):
        # Step 2
        fetch_dht_state_from_file()
        fetch_namespace_from_file()

    elif(option == '--create_index'):
        # Step 3
        create_search_index()

    elif(option == '--optimize'):
        optimize_db()

    elif(option == '--refresh'):
        flush_db()
        fetch_dht_state_from_file()
        fetch_namespace_from_file()
        create_search_index()

    else:
        print "Usage error"
