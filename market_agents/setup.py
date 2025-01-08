from setuptools import setup, find_packages

setup(
    name="market_agents",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "pydantic",
        "asyncio",
    ],
    include_package_data=True
)