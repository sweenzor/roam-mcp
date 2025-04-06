from setuptools import setup, find_packages

setup(
    name="mcp-server-roam",
    version="0.1.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "mcp[cli]>=0.20.0",
    ],
    extras_require={
        "dev": [
            "pytest",
            "black",
            "mypy",
            "ruff",
        ]
    },
    python_requires=">=3.10",
)