# Copyright 2026 David Wies
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from importlib.metadata import version, PackageNotFoundError

try:
    _version = version("geosketch")
except PackageNotFoundError:
    _version = "unknown"


def main() -> None:
    print(f"GeoSketch v{_version} — UI not yet implemented")


if __name__ == "__main__":
    main()
