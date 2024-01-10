# Author: Teppei Fukutomi <https://github.com/T3pp31>
# Copyright (C) 2024- Teppei Fukutomi
# License: MIT

from setuptools import setup

import easy_blockchain

DESCRIPTION = 'Easy Blockchain: A simple blockchain implementation in Python.'
NAME = 'easy_blockchain'
AUTHOR = 'Teppei Fukutomi'
AUTHOR_EMAIL = 'teppei.fukutomi@gmail.com'
URL = 'https://github.com/T3pp31/easy_blockchain'
LICENSE = 'MIT'
DOWNLOAD_URL = 'https://github.com/T3pp31/easy_blockchain'
VERION = easy_blockchain.__version__
PYTHON_REQUIRES = '>=3.9'

INSTALL_REQUIRES = [
    'hashlib',
    'json',
    'datetime',
    'os'
]

EXTRAS_REQUIRE = {}

PACKAGES = [
    'easy_blockchain'
]

CLASSIFIERS = [
    'Programming Language :: Python :: 3',
    'License :: OSI Approved :: MIT License',
    'Operating System :: OS Independent',
    'Topic :: Software Development :: Libraries :: Python Modules'

]

with open("README.md", 'r') as fp:
    readme = fp.read()

long_description = readme

setup(name=NAME,
      author=AUTHOR,
      author_email=AUTHOR_EMAIL,
      maintainer=AUTHOR,
      maintainer_email=AUTHOR_EMAIL,
      description=DESCRIPTION,
      long_description=long_description,
      license=LICENSE,
      url=URL,
      version=VERION,
      download_url=DOWNLOAD_URL,
      python_requires=PYTHON_REQUIRES,
      install_requires=INSTALL_REQUIRES,
      extras_require=EXTRAS_REQUIRE,
      packages=PACKAGES,
      classifiers=CLASSIFIERS)
