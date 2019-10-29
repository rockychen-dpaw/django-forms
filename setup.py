from setuptools import setup, find_packages

setup(
    name='django-mvc',
    version='1.0.1',
    packages=find_packages(),
    description='Enhanced mvc framework for Django/Python apps',
    url='https://github.com/rockychen-dpaw/django-mvc',
    author='Rocky Chen',
    author_email='rocky.chen@dbca.wa.gov.au',
    license='Apache License, Version 2.0',
    zip_safe=False,
    install_requires=[
        'django>=2.2.0'
    ]
)
