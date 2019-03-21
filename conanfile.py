#!/usr/bin/env python
# -*- coding: utf-8 -*-

from conans import ConanFile, CMake, tools
from glob import glob
import os, re, tempfile, requests, hashlib


def _load_possible_targets(version):
    result = []
    url = "https://raw.githubusercontent.com/xianyi/OpenBLAS/v%s/TargetList.txt" % version
    target_list = requests.get(url).text
    actual_digest = hashlib.sha256(target_list).hexdigest()
    expected_digest = "383b9fb0113801fa00efbb9c80f5dd90ded99c893b3164a86e27289400600bde"
    if not actual_digest == expected_digest:
        raise Exception("The computed digest (%s) fot %s is not equal to the expected digest (%s)" % (
        url, actual_digest, expected_digest))
    pattern = re.compile("^[A-Z]+$")
    for line in target_list.split('\n'):
        match = pattern.match(line)
        if match:
            result.append(match.group(0))
    return result


class OpenblasConan(ConanFile):
    name = "openblas"
    version = "0.3.5"
    url = "https://github.com/xianyi/OpenBLAS"
    homepage = "http://www.openblas.net/"
    description = "OpenBLAS is an optimized BLAS library based on GotoBLAS2 1.13 BSD version."
    license = "BSD 3-Clause"
    exports_sources = ["LICENSE", "TargetList.txt"]
    settings = "os", "arch", "compiler", "build_type"

    _targets = _load_possible_targets(version)
    options = {
        "shared": [True, False],
        "USE_MASS": [True, False],
        "USE_OPENMP": [True, False],
        "NO_LAPACKE": [True, False],
        "NOFORTRAN": [True, False],
        "TARGET": _targets

    }
    default_options = "shared=True", "USE_MASS=False", "USE_OPENMP=False", "NO_LAPACKE=True", "NOFORTRAN=False", "TARGET=%s" % \
                      _targets[0]

    def _get_make_arch(self):
        return "32" if self.settings.arch == "x86" else "64"

    def _get_make_build_type_debug(self):
        return "0" if self.settings.build_type == "Release" else "1"

    @staticmethod
    def _get_make_option_value(option):
        return "1" if option else "0"

    def build_requirements(self):
        if self.settings.os == "Windows":
            self.build_requires("strawberryperl/5.26.0@conan/stable")

    def configure(self):
        if self.settings.compiler == "Visual Studio":
            if not self.options.shared:
                raise Exception("Static build not supported in Visual Studio: "
                                "https://github.com/xianyi/OpenBLAS/blob/v0.3.5/CMakeLists.txt#L152")

        if self.settings.os == "Windows":
            if self.options.NOFORTRAN:
                self.output.warn("NOFORTRAN option is disabled for Windows. Setting to false")
                self.options.NOFORTRAN = False

    def source(self):
        self.output.info("source()")
        source_url = "https://sourceforge.net/projects/openblas"
        file_name = ("{0} {1} version".format("OpenBLAS", self.version))
        tools.get("{0}/files/v{1}/{2}.tar.gz".format(source_url, self.version, file_name))
        os.rename(glob("xianyi-OpenBLAS-*")[0], "sources")

    @property
    def _is_msvc(self):
        return self.settings.compiler == "Visual Studio"

    def _configure_cmake(self):
        self.output.warn("Building with CMake: Some options won't make any effect")
        cmake = CMake(self)
        cmake.definitions["USE_MASS"] = self.options.USE_MASS
        cmake.definitions["USE_OPENMP"] = self.options.USE_OPENMP
        cmake.definitions["NO_LAPACKE"] = self.options.NO_LAPACKE
        cmake.definitions["NOFORTRAN"] = self.options.NOFORTRAN
        cmake.configure(source_dir="sources")
        return cmake

    def _build_cmake(self):
        cmake = self._configure_cmake()
        cmake.build()

    def _build_make(self, args=None):
        make_options = ["DEBUG=%s" % self._get_make_build_type_debug(),
                        "BINARY=%s" % self._get_make_arch(),
                        "NO_LAPACKE=%s" % self._get_make_option_value(self.options.NO_LAPACKE),
                        "USE_MASS=%s" % self._get_make_option_value(self.options.USE_MASS),
                        "USE_OPENMP=%s" % self._get_make_option_value(self.options.USE_OPENMP),
                        "NOFORTRAN=%s" % self._get_make_option_value(self.options.NOFORTRAN)]
        if self.options.shared:
            make_options.append("NO_STATIC=1")
        else:
            make_options.append("NO_SHARED=1")
        # https://github.com/xianyi/OpenBLAS/wiki/How-to-build-OpenBLAS-for-Android
        target = self.options.TARGET
        if tools.cross_building(self.settings):
            if "CC_FOR_BUILD" in os.environ:
                hostcc = os.environ["CC_FOR_BUILD"]
            else:
                hostcc = tools.which("cc") or tools.which("gcc") or tools.which("clang")
            make_options.append("HOSTCC=%s" % hostcc)
        if target:
            make_options.append("TARGET=%s" % target)
        if "CC" in os.environ:
            make_options.append("CC=%s" % os.environ["CC"])
        if "AR" in os.environ:
            make_options.append("AR=%s" % os.environ["AR"])
        if args:
            make_options.extend(args)
        self.run("cd sources && make %s" % ' '.join(make_options), cwd=self.source_folder)

    def build(self):
        if self._is_msvc:
            self._build_cmake()
        else:
            self._build_make()

    def package(self):
        if not self._is_msvc:
            self._build_make(args=['PREFIX=%s' % self.package_folder, 'install'])
        else:
            cmake = self._configure_cmake()
            cmake.install()

        with tools.chdir("sources"):
            self.copy(pattern="LICENSE", dst="licenses", src="sources",
                      ignore_case=True, keep_path=False)

    def package_info(self):
        self.cpp_info.libs = tools.collect_libs(self)
        if self._is_msvc:
            self.cpp_info.includedirs.append(os.path.join("include", "openblas"))

        if self.settings.os == "Linux":
            self.cpp_info.libs.append("pthread")
            if not self.options.NOFORTRAN:
                self.cpp_info.libs.append("gfortran")
