============
Contributing
============

Please read the `PIC-SURE contributing guide
<https://github.com/hms-dbmi/pic-sure/blob/main/CONTRIBUTING.md>`_ first. It covers the code of
conduct, filing issues, and how pull requests are reviewed across every PIC-SURE repository.

Building and testing this repo
------------------------------

.. code-block:: shell

    python -m unittest discover tests

The package source is in ``PicSureHpdsLib``. The ``Makefile`` and ``tox.ini`` in this repository are
unmaintained cookiecutter scaffolding: ``make test`` calls ``python setup.py test``, which setuptools
removed in 2024, ``tox.ini`` targets Python 3.4 through 3.6, and ``make lint`` points at a directory
that does not exist. Do not rely on them.
