from setuptools import setup, find_packages

setup(
    name='django-forms',
    version='1.0.0',
    packages=find_packages(),
    description='Enhanced form framework for Django/Python apps',
    url='https://github.com/rockychen-dpaw/django-forms',
    author='Rocky Chen',
    author_email='rocky.chen@dbca.wa.gov.au',
    license='Apache License, Version 2.0',
    zip_safe=False,
    install_requires=[
        'django>=2.2.0'
    ]
)
