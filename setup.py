import pathlib
from setuptools import setup

# The directory containing this file
HERE = pathlib.Path(__file__).parent

# The text of the README file
README = (HERE / "README.md").read_text()

# This call to setup() does all the work
setup(
    name="mythic_payloadtype_container",
    version="0.1.0",
    description="Functionality for Mythic Payload Type Containers",
    long_description=README,
    long_description_content_type="text/markdown",
    url="https://docs.mythic-c2.net/customizing/payload-type-development",
    author="@its_a_feature_",
    author_email="",
    license="BSD3",
    classifiers=[
        "License :: Other/Proprietary License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
    ],
    packages=["mythic_payloadtype_container"],
    include_package_data=True,
    install_requires=["aio_pika", "dynaconf"],
    entry_points={
    },
)
