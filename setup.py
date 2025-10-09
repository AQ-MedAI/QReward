import os
import sys
from shutil import rmtree

from setuptools import Command, find_packages, setup

# RELEASE STEPS
# $ python setup.py upload


__title__ = "qreward"
__description__ = ("RewardService Python Client, "
                   "make RL Training reward function easier")
__url__ = "https://github.com/AQ-MedAI/QReward"
__author_email__ = "379978424@qq.com"
__license__ = "LEGAL.md"

__requires__ = [
    "openai",
    "aiohttp",
    "httpx-aiohttp",
    "httpx",
    "aiodns",
    "tenacity",
    "aiolimiter",
    "requests",
]

__keywords__ = [
    "Reward",
    "RL",
    "Reinforcement Learning",
    "Reward Service",
]

# Load the package's _version.py module as a dictionary.
here = os.path.abspath(os.path.dirname(__file__))
about = {}
with open(os.path.join(here, __title__, "_version.py")) as f:
    exec(f.read(), about)


__version__ = about["__version__"]


class UploadCommand(Command):
    description = "Build and publish the package."
    user_options = []

    @staticmethod
    def status(s):
        print("✨✨ {0}".format(s))

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        try:
            self.status("Removing previous builds…")
            rmtree(os.path.join(here, "dist"))
            rmtree(os.path.join(here, "build"))
            rmtree(os.path.join(here, "{0}.egg-info".format(__title__)))
        except OSError:
            pass

        self.status("Building Source and Wheel distribution…")
        os.system("{0} setup.py sdist bdist_wheel".format(sys.executable))

        self.status("Uploading the package to PyPI via Twine…")
        os.system("twine upload dist/*")

        self.status("Pushing git tags…")
        os.system('git tag -a v{0} -m "release version v{0}"'.format(
            __version__,
        ))
        os.system("git push origin v{0}".format(__version__))

        sys.exit()


setup(
    name=__title__,
    version=__version__,
    description=__description__,
    url=__url__,
    author=about["__author__"],
    author_email=__author_email__,
    maintainer=about["__author__"],
    maintainer_email=__author_email__,
    license=__license__,
    packages=find_packages(exclude=("test",)),
    keywords=__keywords__,
    install_requires=__requires__,
    zip_safe=False,
    include_package_data=True,
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "Intended Audience :: Information Technology",
        "Intended Audience :: System Administrators",
        "Operating System :: MacOS",
        "Operating System :: POSIX :: Linux",
        "Operating System :: Unix",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Utilities",
        "Typing :: Typed",
    ],
    cmdclass={"upload": UploadCommand},
    # extras_require=__extra_requires__,
)
