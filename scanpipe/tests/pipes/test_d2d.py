# SPDX-License-Identifier: Apache-2.0
#
# http://nexb.com and https://github.com/nexB/scancode.io
# The ScanCode.io software is licensed under the Apache License version 2.0.
# Data generated with ScanCode.io is provided as-is without warranties.
# ScanCode is a trademark of nexB Inc.
#
# You may not use this software except in compliance with the License.
# You may obtain a copy of the License at: http://apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.
#
# Data Generated with ScanCode.io is provided on an "AS IS" BASIS, WITHOUT WARRANTIES
# OR CONDITIONS OF ANY KIND, either express or implied. No content created from
# ScanCode.io should be considered or used as legal advice. Consult an Attorney
# for any legal advice.
#
# ScanCode.io is a free software code scanning tool from nexB Inc. and others.
# Visit https://github.com/nexB/scancode.io for support and download.

import io
import tempfile
import uuid
from pathlib import Path
from unittest import mock

from django.test import TestCase

from scanpipe import pipes
from scanpipe.models import CodebaseResource
from scanpipe.models import Project
from scanpipe.pipes import d2d
from scanpipe.pipes import flag
from scanpipe.pipes.input import copy_input
from scanpipe.pipes.input import copy_inputs
from scanpipe.tests import make_resource_directory
from scanpipe.tests import make_resource_file
from scanpipe.tests import package_data1


class ScanPipeD2DPipesTest(TestCase):
    data_location = Path(__file__).parent.parent / "data"

    def setUp(self):
        self.project1 = Project.objects.create(name="Analysis")

    def test_scanpipe_pipes_d2d_get_inputs(self):
        with self.assertRaises(FileNotFoundError) as error:
            d2d.get_inputs(self.project1)
        self.assertEqual("from* input files not found.", str(error.exception))

        _, input_location = tempfile.mkstemp(prefix="from-")
        self.project1.copy_input_from(input_location)

        with self.assertRaises(FileNotFoundError) as error:
            d2d.get_inputs(self.project1)
        self.assertEqual("to* input files not found.", str(error.exception))

        _, input_location = tempfile.mkstemp(prefix="to-")
        self.project1.copy_input_from(input_location)

        from_files, to_files = d2d.get_inputs(self.project1)
        self.assertEqual(1, len(from_files))
        self.assertEqual(1, len(to_files))

        _, input_location = tempfile.mkstemp(prefix="from-")
        self.project1.copy_input_from(input_location)
        _, input_location = tempfile.mkstemp(prefix="to-")
        self.project1.copy_input_from(input_location)
        from_files, to_files = d2d.get_inputs(self.project1)
        self.assertEqual(2, len(from_files))
        self.assertEqual(2, len(to_files))

    def test_scanpipe_pipes_d2d_get_extracted_path(self):
        path = "not/an/extracted/path/"
        r1 = make_resource_file(self.project1, path)
        expected = "not/an/extracted/path/-extract/"
        self.assertEqual(expected, d2d.get_extracted_path(r1))

        path = "a.jar-extract/subpath/file.ext"
        r2 = make_resource_file(self.project1, path)
        expected = "a.jar-extract/subpath/file.ext-extract/"
        self.assertEqual(expected, d2d.get_extracted_path(r2))

    def test_scanpipe_pipes_d2d_get_extracted_subpath(self):
        path = "not/an/extracted/path/"
        self.assertEqual(path, d2d.get_extracted_subpath(path))

        path = "a.jar-extract/subpath/file.ext"
        self.assertEqual("subpath/file.ext", d2d.get_extracted_subpath(path))

        path = "a.jar-extract/subpath/b.jar-extract/subpath/file.ext"
        self.assertEqual("subpath/file.ext", d2d.get_extracted_subpath(path))

    @mock.patch("scanpipe.pipes.purldb.match_packages")
    def test_scanpipe_pipes_d2d_match_purldb_resources(self, mock_match_package):
        to_1 = make_resource_file(self.project1, "to/package.jar", sha1="abcdef")
        to_1.is_archive = True
        to_1.save()
        # The initial status will be updated to flag.MATCHED_TO_PURLDB
        to_2 = make_resource_file(
            self.project1, "to/package.jar-extract/a.class", status=flag.MAPPED
        )
        to_3 = make_resource_file(self.project1, "to/package.jar-extract/b.class")

        package_data = package_data1.copy()
        package_data["uuid"] = uuid.uuid4()
        package_data["sha1"] = "abcdef"
        mock_match_package.return_value = [package_data]

        buffer = io.StringIO()
        d2d.match_purldb_resources(
            self.project1,
            extensions=[".jar"],
            matcher_func=d2d.match_purldb_package,
            logger=buffer.write,
        )
        expected = (
            "Matching 1 .jar resources in PurlDB, using SHA1"
            "3 resources matched in PurlDB using 1 SHA1s"
        )
        self.assertEqual(expected, buffer.getvalue())

        package = self.project1.discoveredpackages.get()
        self.assertEqual(package_data["name"], package.name)
        self.assertNotEqual(package_data["uuid"], package.uuid)

        for resource in [to_1, to_2, to_3]:
            resource.refresh_from_db()
            self.assertEqual(flag.MATCHED_TO_PURLDB, resource.status)
            self.assertEqual(package, resource.discovered_packages.get())

    @mock.patch("scanpipe.pipes.purldb.request_get")
    def test_scanpipe_pipes_d2d_match_purldb_directories(self, mock_request_get):
        to_1 = make_resource_directory(
            self.project1,
            "to/package.jar-extract",
            extra_data={"directory_content": "abcdef"},
        )
        to_2 = make_resource_file(self.project1, "to/package.jar-extract/a.class")
        to_3 = make_resource_file(self.project1, "to/package.jar-extract/b.class")
        package_data = package_data1.copy()
        package_data["uuid"] = uuid.uuid4()
        mock_request_get.side_effect = [
            [
                {
                    "fingerprint": "abcdef",
                    "matched_fingerprint": "abcdef",
                    "package": "http://private.purldb.io/api/packages/package-id-123",
                }
            ],
            package_data,
            [],
        ]

        buffer = io.StringIO()
        d2d.match_purldb_directories(
            self.project1,
            logger=buffer.write,
        )

        expected = (
            "Matching 1 directory from to/ in PurlDB" "1 directory matched in PurlDB"
        )
        self.assertEqual(expected, buffer.getvalue())

        package = self.project1.discoveredpackages.get()
        self.assertEqual(package_data["name"], package.name)
        self.assertNotEqual(package_data["uuid"], package.uuid)

        for resource in [to_1, to_2, to_3]:
            resource.refresh_from_db()
            self.assertEqual("matched-to-purldb", resource.status)
            self.assertEqual(package, resource.discovered_packages.get())

    def test_scanpipe_pipes_d2d_get_best_path_matches_same_name(self):
        to_1 = CodebaseResource(name="package-1.0.ext", path="to/package-1.0.ext")
        to_2 = CodebaseResource(name="package-2.0.ext", path="to/package-2.0.ext")
        from_1 = CodebaseResource(name="package-1.0.ext", path="from/package-1.0.ext")
        from_2 = CodebaseResource(name="package-2.0.ext", path="from/package-2.0.ext")
        matches = [from_1, from_2]
        self.assertEqual([from_1], d2d.get_best_path_matches(to_1, matches))
        self.assertEqual([from_2], d2d.get_best_path_matches(to_2, matches))

    def test_scanpipe_pipes_d2d_get_best_path_matches_extracted_subpath(self):
        to_1 = CodebaseResource(path="to/jar-extract/a/package-1.0.ext")
        to_2 = CodebaseResource(path="to/jar-extract/a/package-2.0.ext")
        from_1 = CodebaseResource(path="from/src/a/package-1.0.ext")
        from_2 = CodebaseResource(path="from/src/a/package-2.0.ext")
        matches = [from_1, from_2]
        self.assertEqual([from_1], d2d.get_best_path_matches(to_1, matches))
        self.assertEqual([from_2], d2d.get_best_path_matches(to_2, matches))

    def test_scanpipe_pipes_d2d_get_best_path_matches(self):
        to_1 = make_resource_file(self.project1, path="to/a/b/c/file.txt")
        from_1 = make_resource_file(self.project1, path="from/source/f/i/j/file.txt")
        from_2 = make_resource_file(self.project1, path="from/source/a/b/c/file.txt")
        from_3 = make_resource_file(self.project1, path="from/q/w/e/file.txt")

        matches = [from_1, from_2, from_3]
        self.assertEqual([from_2], d2d.get_best_path_matches(to_1, matches))

        # Cannot determine the best as only the filename matches
        to_2 = make_resource_file(self.project1, path="to/x/y/z/init.jsp.readme")
        self.assertEqual(matches, d2d.get_best_path_matches(to_2, matches))

    def test_scanpipe_pipes_d2d_map_checksum(self):
        sha1 = "abcde"
        to_1 = make_resource_file(self.project1, path="to/a/b/c/file.txt", sha1=sha1)
        make_resource_file(self.project1, path="from/source/f/i/j/file.txt", sha1=sha1)
        from_2 = make_resource_file(
            self.project1, path="from/source/a/b/c/file.txt", sha1=sha1
        )
        # Matchable path but missing sha1 value
        make_resource_file(self.project1, path="from/content/a/b/c/file.txt")
        make_resource_file(self.project1, path="from/q/w/e/file.txt", sha1=sha1)

        buffer = io.StringIO()
        d2d.map_checksum(self.project1, "sha1", logger=buffer.write)
        expected = "Mapping 1 to/ resources using sha1 against from/ codebase"
        self.assertEqual(expected, buffer.getvalue())
        self.assertEqual(1, to_1.related_from.count())
        relation = to_1.related_from.get()
        self.assertEqual("sha1", relation.map_type)
        self.assertEqual(from_2, relation.from_resource)

    def test_scanpipe_pipes_d2d_flag_processed_archives(self):
        to_archive = make_resource_file(
            self.project1, path="to/archive.lpkg", is_archive=True
        )
        make_resource_directory(
            self.project1, path="to/archive.lpkg-extract", status=flag.IGNORED_DIRECTORY
        )
        make_resource_file(
            self.project1,
            path="to/archive.lpkg-extract/file1.txt",
            status=flag.MATCHED_TO_PURLDB,
        )
        make_resource_file(
            self.project1,
            path="to/archive.lpkg-extract/file2.txt",
            status=flag.MATCHED_TO_PURLDB,
        )

        d2d.flag_processed_archives(self.project1)
        to_archive.refresh_from_db()
        self.assertEqual(flag.ARCHIVE_PROCESSED, to_archive.status)

        to_archive.update(status="")
        make_resource_file(
            self.project1,
            path="to/archive.lpkg-extract/file3.txt",
        )
        d2d.flag_processed_archives(self.project1)
        to_archive.refresh_from_db()
        self.assertEqual("", to_archive.status)

    def test_scanpipe_pipes_d2d_map_java_to_class(self):
        from1 = make_resource_file(
            self.project1,
            path="from/flume-ng-node-1.9.0-sources.jar-extract/org/apache/flume/node/"
            "AbstractConfigurationProvider.java",
            extra_data={"java_package": "org.apache.flume.node"},
        )
        from2 = make_resource_file(
            self.project1,
            path="from/flume-ng-node-1.9.0-sources.jar-extract/org/apache/flume/WRONG/"
            "Application.java",
            extra_data={"java_package": "org.apache.flume.WRONG"},
        )
        to1 = make_resource_file(
            self.project1,
            path="to/flume-ng-node-1.9.0.jar-extract/org/apache/flume/node/"
            "AbstractConfigurationProvider$ChannelComponent.class",
        )
        to2 = make_resource_file(
            self.project1,
            path="to/flume-ng-node-1.9.0.jar-extract/org/apache/flume/node/"
            "AbstractConfigurationProvider.class",
        )
        to3 = make_resource_file(
            self.project1,
            path="to/flume-ng-node-1.9.0.jar-extract/org/apache/flume/node/"
            "Application.class",
        )

        buffer = io.StringIO()
        d2d.map_java_to_class(self.project1, logger=buffer.write)

        expected = "Mapping 3 .class resources to .java"
        self.assertIn(expected, buffer.getvalue())

        self.assertEqual(2, self.project1.codebaserelations.count())

        r1 = self.project1.codebaserelations.get(to_resource=to1, from_resource=from1)
        self.assertEqual("java_to_class", r1.map_type)
        expected = {"from_source_root": "from/flume-ng-node-1.9.0-sources.jar-extract/"}
        self.assertEqual(expected, r1.extra_data)

        r2 = self.project1.codebaserelations.get(to_resource=to2, from_resource=from1)
        self.assertEqual("java_to_class", r2.map_type)
        expected = {"from_source_root": "from/flume-ng-node-1.9.0-sources.jar-extract/"}
        self.assertEqual(expected, r2.extra_data)

        no_relations = self.project1.codebaseresources.has_no_relation()
        self.assertIn(from2, no_relations)
        self.assertIn(to3, no_relations)
        to3.refresh_from_db()
        self.assertEqual("", to3.status)

    def test_scanpipe_pipes_d2d_map_java_to_class_no_java(self):
        make_resource_file(self.project1, path="to/Abstract.class")
        buffer = io.StringIO()
        d2d.map_java_to_class(self.project1, logger=buffer.write)
        expected = "Mapping 1 .class resources to .java" "No .java resources to map."
        self.assertIn(expected, buffer.getvalue())

    def test_scanpipe_pipes_d2d_map_jar_to_source(self):
        from1 = make_resource_file(
            self.project1,
            path="from/flume-ng-node-1.9.0-sources.jar-extract/org/apache/flume/node/"
            "AbstractConfigurationProvider.java",
            extra_data={"java_package": "org.apache.flume.node"},
        )
        from2 = make_resource_file(
            self.project1,
            path="from/flume-ng-node-1.9.0-sources.jar-extract",
        )
        to1 = make_resource_file(
            self.project1,
            path="to/flume-ng-node-1.9.0.jar-extract/org/apache/flume/node/"
            "AbstractConfigurationProvider.class",
        )
        make_resource_file(
            self.project1,
            path="to/flume-ng-node-1.9.0.jar-extract/META-INF/MANIFEST.MF",
        )
        to_jar = make_resource_file(
            self.project1,
            path="to/flume-ng-node-1.9.0.jar",
        )

        buffer = io.StringIO()
        d2d.map_java_to_class(self.project1, logger=buffer.write)
        relation = self.project1.codebaserelations.get()
        self.assertEqual(from1, relation.from_resource)
        self.assertEqual(to1, relation.to_resource)
        self.assertEqual("java_to_class", relation.map_type)
        expected = {"from_source_root": "from/flume-ng-node-1.9.0-sources.jar-extract/"}
        self.assertEqual(expected, relation.extra_data)

        buffer = io.StringIO()
        with self.assertNumQueries(6):
            d2d.map_jar_to_source(self.project1, logger=buffer.write)
        expected = "Mapping 1 .jar resources using map_jar_to_source"
        self.assertIn(expected, buffer.getvalue())

        self.assertEqual(2, self.project1.codebaserelations.count())
        relation = self.project1.codebaserelations.get(map_type="jar_to_source")
        self.assertEqual(from2, relation.from_resource)
        self.assertEqual(to_jar, relation.to_resource)

    def test_scanpipe_pipes_d2d_map_jar_to_source_works_for_jar(self):
        from1 = make_resource_file(
            self.project1,
            path="from/org/apache/logging/log4j/core/util/SystemClock.java",
            extra_data={"java_package": "org.apache.logging.log4j.core.util"},
        )
        to1 = make_resource_file(
            self.project1,
            path=(
                "to/META-INF/versions/9/org/apache/logging/log4j/core/util/"
                "SystemClock.class"
            ),
        )
        to2 = make_resource_file(
            self.project1,
            path="to/org/apache/logging/log4j/core/util/SystemClock.class",
        )

        d2d.map_java_to_class(self.project1)

        expected = [
            (from1.path, to1.path, "java_to_class"),
            (from1.path, to2.path, "java_to_class"),
        ]

        results = list(
            self.project1.codebaserelations.all().values_list(
                "from_resource__path", "to_resource__path", "map_type"
            )
        )

        self.assertEqual(expected, results)

    def test_scanpipe_pipes_d2d_get_indexable_qualified_java_paths_from_values_yields_correct_paths(  # NOQA: E501
        self,
    ):
        resource_values = [
            (
                1,
                "SystemClock.java",
                {"java_package": "org.apache.logging.log4j.core.util"},
            ),
            (
                2,
                "SystemClock2.java",
                {"java_package": "org.apache.logging.log4j.core.util"},
            ),
        ]
        expected = [
            (1, "org/apache/logging/log4j/core/util/SystemClock.java"),
            (2, "org/apache/logging/log4j/core/util/SystemClock2.java"),
        ]
        results = list(
            d2d.get_indexable_qualified_java_paths_from_values(resource_values)
        )
        self.assertEqual(expected, results)

    def test_scanpipe_pipes_d2d_map_path(self):
        from1 = make_resource_file(
            self.project1,
            path="from/core/src/main/org/apache/bar/file.ext",
        )
        make_resource_file(
            self.project1,
            path="from/core/src/main/org/apache2/bar/file.ext",
        )
        make_resource_file(
            self.project1,
            path="from/core/src/main/org/apache/bar/file2.ext",
        )
        to1 = make_resource_file(
            self.project1,
            path="to/apache/bar/file.ext",
        )
        make_resource_file(
            self.project1,
            path="to/apache/foo/file.ext",
        )

        buffer = io.StringIO()
        d2d.map_path(self.project1, logger=buffer.write)
        expected = "Mapping 2 to/ resources using path map against from/ codebase"
        self.assertIn(expected, buffer.getvalue())
        file_name_too_many = self.project1.codebaseresources.get(
            path="to/apache/foo/file.ext"
        )

        self.assertEqual(1, self.project1.codebaserelations.count())
        relation = self.project1.codebaserelations.get()
        self.assertEqual(from1, relation.from_resource)
        self.assertEqual(to1, relation.to_resource)
        self.assertEqual("path", relation.map_type)
        self.assertEqual({"path_score": "3/3"}, relation.extra_data)
        self.assertNotEqual("too-many-maps", file_name_too_many.status)

    def test_scanpipe_pipes_d2d_find_java_packages(self):
        input_locations = [
            self.data_location / "d2d" / "find_java_packages" / "Foo.java",
            self.data_location / "d2d" / "find_java_packages" / "Baz.java",
            self.data_location / "d2d" / "find_java_packages" / "Baz.class",
        ]

        from_dir = self.project1.codebase_path / "from"
        from_dir.mkdir()
        copy_inputs(input_locations, from_dir)
        pipes.collect_and_create_codebase_resources(self.project1)

        buffer = io.StringIO()
        d2d.find_java_packages(self.project1, logger=buffer.write)

        expected = "Finding Java package for 2 .java resources."
        self.assertEqual(expected, buffer.getvalue())

        expected = [
            {"extra_data": {}, "path": "from"},
            {"extra_data": {}, "path": "from/Baz.class"},
            {"extra_data": {"java_package": "org.apache.biz"}, "path": "from/Baz.java"},
            {"extra_data": {"java_package": "org.apache.foo"}, "path": "from/Foo.java"},
        ]
        results = list(self.project1.codebaseresources.values("path", "extra_data"))
        self.assertEqual(expected, results)

    def test_scanpipe_pipes_d2d_map_javascript_skips_dot_file(self):
        make_resource_file(
            self.project1,
            path=(
                "from/project.tar.zst/modules/apps/adaptive-media/"
                "adaptive-media-web/src/main/resources/META-INF/resources/"
                "adaptive_media/js/.main.js"
            ),
        )
        d2d.map_javascript(self.project1)
        self.assertEqual(0, self.project1.codebaserelations.count())

    def test_scanpipe_pipes_d2d_map_javascript(self):
        to_dir = (
            self.project1.codebase_path / "to/project.tar.zst-extract/osgi/marketplace/"
            "intelligent robotics platform.lpkg-extract/"
            "com.example.adaptive.media.web-0.0.5.jar-extract/META-INF/"
            "resources/adaptive_media/js"
        )
        to_dir.mkdir(parents=True)
        resource_files = [
            self.data_location / "d2d-javascript" / "to" / "main.js.map",
            self.data_location / "d2d-javascript" / "to" / "main.js",
        ]
        copy_inputs(resource_files, to_dir)

        from_input_location = self.data_location / "d2d-javascript" / "from" / "main.js"
        from_dir = (
            self.project1.codebase_path
            / "from/project.tar.zst/modules/apps/adaptive-media/"
            "adaptive-media-web/src/main/resources/META-INF/resources/"
            "adaptive_media/js"
        )
        from_dir.mkdir(parents=True)
        copy_input(from_input_location, from_dir)

        pipes.collect_and_create_codebase_resources(self.project1)

        from_resource = self.project1.codebaseresources.get(
            path=(
                "from/project.tar.zst/modules/apps/adaptive-media/"
                "adaptive-media-web/src/main/resources/META-INF/resources/"
                "adaptive_media/js/main.js"
            )
        )

        buffer = io.StringIO()
        d2d.map_javascript(self.project1, logger=buffer.write)
        expected = (
            "Mapping 1 .map resources using javascript map against from/ codebase."
        )
        self.assertIn(expected, buffer.getvalue())

        self.assertEqual(2, self.project1.codebaserelations.count())
        relation = self.project1.codebaserelations.all()
        self.assertEqual(from_resource, relation[0].from_resource)
        self.assertEqual(from_resource, relation[1].from_resource)

    def test_scanpipe_pipes_d2d_map_javascript_works_with_diff_ratio(self):
        to_dir = (
            self.project1.codebase_path / "to/project.tar.zst-extract/osgi/marketplace/"
            "intelligent robotics platform.lpkg-extract/"
            "com.example.adaptive.media.web-0.0.5.jar-extract/META-INF/"
            "resources/adaptive_media/js"
        )
        to_dir.mkdir(parents=True)
        resource_files = [
            self.data_location / "d2d-javascript" / "to" / "unmain.js.map",
            self.data_location / "d2d-javascript" / "to" / "unmain.js",
        ]
        copy_inputs(resource_files, to_dir)

        from_input_location = (
            self.data_location / "d2d-javascript" / "from" / "unmain.js"
        )
        from_dir = (
            self.project1.codebase_path
            / "from/project.tar.zst/modules/apps/adaptive-media/"
            "adaptive-media-web/src/main/resources/META-INF/resources/"
            "adaptive_media/js"
        )
        from_dir.mkdir(parents=True)
        copy_input(from_input_location, from_dir)

        pipes.collect_and_create_codebase_resources(self.project1)

        from_resource = self.project1.codebaseresources.get(
            path=(
                "from/project.tar.zst/modules/apps/adaptive-media/"
                "adaptive-media-web/src/main/resources/META-INF/resources/"
                "adaptive_media/js/unmain.js"
            )
        )

        buffer = io.StringIO()
        d2d.map_javascript(self.project1, logger=buffer.write)
        expected = (
            "Mapping 1 .map resources using javascript map against from/ codebase."
        )
        self.assertIn(expected, buffer.getvalue())

        self.assertEqual(2, self.project1.codebaserelations.count())
        relation = self.project1.codebaserelations.all()
        self.assertEqual(from_resource, relation[0].from_resource)
        self.assertEqual(from_resource, relation[1].from_resource)

    @mock.patch("scanpipe.pipes.purldb.match_resources")
    @mock.patch("scanpipe.pipes.purldb.request_get")
    def test_scanpipe_pipes_d2d_match_js_purldb(self, mock_match_resource, mock_get):
        to_location = self.data_location / "d2d-javascript" / "to" / "unmain.js.map"
        to_dir = (
            self.project1.codebase_path
            / "to/project.tar.zst/modules/apps/adaptive-media/"
            "adaptive-media-web/src/main/resources/META-INF/resources/"
            "adaptive_media/js"
        )
        to_dir.mkdir(parents=True)
        copy_input(to_location, to_dir)

        pipes.collect_and_create_codebase_resources(self.project1)

        mock_get.return_value = [
            {
                "package": "http://example.com/api/packages/xyz/",
                "purl": "pkg:deb/debian/adduser@3.118",
                "path": "package/dist/SassWarning.js",
                "type": "file",
                "sha1": "4bbc6d18a574e11fbdcbb74a24f1956bcedcc170",
            },
            {
                "package": "http://example.com/api/packages/zyx/",
                "purl": "pkg:deb/debian/adduser@3.118",
                "path": "package/dist/SassWarning.js",
                "type": "file",
                "sha1": "d6bfcf7d1f8a00cc639b3a186a52453d37c52f61",
            },
        ]

        package_data = package_data1.copy()
        package_data["uuid"] = uuid.uuid4()
        mock_match_resource.return_value = package_data

        buffer = io.StringIO()
        d2d.match_purldb_resources(
            self.project1,
            extensions=[".map", ".js"],
            matcher_func=d2d.match_purldb_resource,
            logger=buffer.write,
        )
        expected = (
            "Matching 1 .map, .js resources in PurlDB, using SHA1"
            "1 resources matched in PurlDB using 2 SHA1s"
        )
        self.assertEqual(expected, buffer.getvalue())

        package = self.project1.discoveredpackages.get()
        self.assertEqual(package_data["name"], package.name)
        self.assertNotEqual(package_data["uuid"], package.uuid)

    def test_scanpipe_pipes_d2d_map_javascript_post_purldb_match(self):
        to_map = self.data_location / "d2d-javascript" / "to" / "main.js.map"
        to_mini = self.data_location / "d2d-javascript" / "to" / "main.js"
        to_dir = (
            self.project1.codebase_path
            / "to/project.tar.zst/modules/apps/adaptive-media/"
            "adaptive-media-web/src/main/resources/META-INF/resources/"
            "adaptive_media/js"
        )
        to_dir.mkdir(parents=True)
        copy_input(to_mini, to_dir)
        copy_input(to_map, to_dir)

        pipes.collect_and_create_codebase_resources(self.project1)

        to_map_resources = self.project1.codebaseresources.filter(
            path=(
                "to/project.tar.zst/modules/apps/adaptive-media/"
                "adaptive-media-web/src/main/resources/META-INF/resources/"
                "adaptive_media/js/main.js.map"
            )
        )

        package_data = package_data1.copy()
        package_data["uuid"] = uuid.uuid4()

        package, matched_resources_count = d2d.create_package_from_purldb_data(
            self.project1, to_map_resources, package_data
        )

        buffer = io.StringIO()
        d2d.map_javascript_post_purldb_match(
            self.project1,
            logger=buffer.write,
        )
        expected = (
            "Mapping 1 minified .js and .css resources based on existing PurlDB match."
        )
        self.assertEqual(expected, buffer.getvalue())

        result = package.codebase_resources.count()
        self.assertEqual(2, result)

    def test_scanpipe_pipes_d2d_map_javascript_path(self):
        to_dir = (
            self.project1.codebase_path / "to/project.tar.zst-extract/osgi/marketplace/"
            "intelligent robotics platform.lpkg-extract/"
            "com.example.adaptive.media.web-0.0.5.jar-extract/META-INF/"
            "resources/adaptive_media/js"
        )
        to_dir.mkdir(parents=True)
        resource_files = [
            self.data_location / "d2d-javascript" / "to" / "main.js.map",
            self.data_location / "d2d-javascript" / "to" / "main.js",
        ]
        copy_inputs(resource_files, to_dir)

        from_input_location = self.data_location / "d2d-javascript" / "from" / "main.js"
        from_dir = (
            self.project1.codebase_path
            / "from/project.tar.zst/modules/apps/adaptive-media/"
            "adaptive-media-web/src/main/resources/META-INF/resources/"
            "adaptive_media/js"
        )
        from_dir.mkdir(parents=True)
        copy_input(from_input_location, from_dir)

        pipes.collect_and_create_codebase_resources(self.project1)

        from_resource = self.project1.codebaseresources.get(
            path=(
                "from/project.tar.zst/modules/apps/adaptive-media/"
                "adaptive-media-web/src/main/resources/META-INF/resources/"
                "adaptive_media/js/main.js"
            )
        )

        buffer = io.StringIO()
        d2d.map_javascript_path(self.project1, logger=buffer.write)
        expected = "Mapping 1 to/ resources using javascript map against from/ codebase"
        self.assertIn(expected, buffer.getvalue())

        self.assertEqual(2, self.project1.codebaserelations.count())
        relation = self.project1.codebaserelations.all()
        self.assertEqual(from_resource, relation[0].from_resource)
        self.assertEqual(from_resource, relation[1].from_resource)

    def test_scanpipe_pipes_d2d_map_javascript_colocation(self):
        to_dir1 = (
            self.project1.codebase_path / "to/project.tar.zst-extract/osgi/marketplace/"
            "intelligent robotics platform.lpkg-extract/"
            "com.example.adaptive.media.web-0.0.5.jar-extract/META-INF/"
            "resources/adaptive_media/js"
        )
        to_dir1.mkdir(parents=True)
        to_resource_files1 = [
            self.data_location / "d2d-javascript" / "to" / "main.js.map",
            self.data_location / "d2d-javascript" / "to" / "main.js",
        ]
        copy_inputs(to_resource_files1, to_dir1)

        to_resource_file3 = self.data_location / "d2d-javascript" / "to" / "unmain.js"
        to_dir3 = (
            self.project1.codebase_path / "to/project.tar.zst-extract/osgi/marketplace/"
            "intelligent robotics platform.lpkg-extract/"
            "com.example.adaptive.media.web-0.0.5.jar-extract/META-INF/"
            "resources/adaptive_media/jsx"
        )
        to_dir3.mkdir(parents=True)
        copy_input(to_resource_file3, to_dir3)

        from_input_location = self.data_location / "d2d-javascript" / "from" / "main.js"
        from_dir1 = (
            self.project1.codebase_path
            / "from/project.tar.zst/modules/apps/adaptive-media/"
            "adaptive-media-web/src/main/resources/META-INF/resources/"
            "adaptive_media/js"
        )
        from_dir1.mkdir(parents=True)
        copy_input(from_input_location, from_dir1)

        from_dir2 = (
            self.project1.codebase_path
            / "from/project.tar.zst/modules/apps/adaptive-media/"
            "ambiguous-machine-cloud/src/main/resources/META-INF/resources/"
            "adaptive_media/js"
        )
        from_dir2.mkdir(parents=True)
        copy_input(from_input_location, from_dir2)

        from_dir3 = (
            self.project1.codebase_path
            / "from/project.tar.zst/modules/apps/adaptive-media/"
            "adaptive-media-web/src/main/resources/META-INF/resources/"
            "adaptive_media/jsx"
        )
        from_dir3.mkdir(parents=True)
        copy_input(from_input_location, from_dir3)

        pipes.collect_and_create_codebase_resources(self.project1)

        from_resource1 = self.project1.codebaseresources.get(
            path=(
                "from/project.tar.zst/modules/apps/adaptive-media/"
                "adaptive-media-web/src/main/resources/META-INF/resources/"
                "adaptive_media/js/main.js"
            )
        )
        to_resource1 = self.project1.codebaseresources.get(
            path=(
                "to/project.tar.zst-extract/osgi/marketplace/"
                "intelligent robotics platform.lpkg-extract/"
                "com.example.adaptive.media.web-0.0.5.jar-extract/META-INF/"
                "resources/adaptive_media/js/main.js"
            )
        )

        from_resource3 = self.project1.codebaseresources.get(
            path=(
                "from/project.tar.zst/modules/apps/adaptive-media/"
                "adaptive-media-web/src/main/resources/META-INF/resources/"
                "adaptive_media/jsx/main.js"
            )
        )
        to_resource3 = self.project1.codebaseresources.get(
            path=(
                "to/project.tar.zst-extract/osgi/marketplace/"
                "intelligent robotics platform.lpkg-extract/"
                "com.example.adaptive.media.web-0.0.5.jar-extract/META-INF/"
                "resources/adaptive_media/jsx/unmain.js"
            )
        )

        pipes.make_relation(
            from_resource=from_resource1,
            to_resource=to_resource1,
            map_type="js_compiled",
        )

        pipes.make_relation(
            from_resource=from_resource3,
            to_resource=to_resource3,
            map_type="js_compiled",
        )

        buffer = io.StringIO()
        d2d.map_javascript_colocation(self.project1, logger=buffer.write)
        expected = (
            "Mapping 1 to/ resources against from/ codebase "
            "based on neighborhood file mapping."
        )

        relation = self.project1.codebaserelations.filter(
            to_resource__path=(
                "to/project.tar.zst-extract/osgi/marketplace/"
                "intelligent robotics platform.lpkg-extract/"
                "com.example.adaptive.media.web-0.0.5.jar-extract/META-INF/"
                "resources/adaptive_media/js/main.js.map"
            ),
        )
        from_expected = self.project1.codebaseresources.get(
            path=(
                "from/project.tar.zst/modules/apps/adaptive-media/"
                "adaptive-media-web/src/main/resources/META-INF/resources/"
                "adaptive_media/js/main.js"
            )
        )

        self.assertIn(expected, buffer.getvalue())
        self.assertEqual(from_expected, relation[0].from_resource)

    def test_map_thirdparty_npm_packages(self):
        to_dir = (
            self.project1.codebase_path / "to/project.tar.zst-extract/osgi/marketplace/"
            "resources/node_modules/foo-bar"
        )
        to_input_location = self.data_location / "d2d-javascript/to/package.json"
        to_dir.mkdir(parents=True)
        copy_input(to_input_location, to_dir)

        pipes.collect_and_create_codebase_resources(self.project1)

        buffer = io.StringIO()
        d2d.map_thirdparty_npm_packages(self.project1, logger=buffer.write)

        package_json = self.project1.codebaseresources.get(
            path=(
                "to/project.tar.zst-extract/osgi/marketplace/"
                "resources/node_modules/foo-bar/package.json"
            )
        )

        expected = (
            "Mapping 1 to/ resources against from/ codebase "
            "based on package.json metadata."
        )
        self.assertIn(expected, buffer.getvalue())

        self.assertEqual(1, self.project1.discoveredpackages.count())
        self.assertEqual("npm-package-lookup", package_json.status)
