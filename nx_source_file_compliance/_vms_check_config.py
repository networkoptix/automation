from ._generic_repo_check_config import RepoCheckConfig

VMS_REPO_CONFIG = RepoCheckConfig(
    opensource_roots=["open", "open_candidate"],
    excluded_dirs={
        "open/licenses",
        "open/artifacts",
        "open/conan_config",
        "open_candidate/artifacts",
    },
    excluded_file_paths={
        "open/readme.md",
        "open/requirements.txt",
        "open/build_info.txt",
        "open/vms/distribution/unit_tests/build_distribution_conf.py.in",
        "open/libs/nx_utils/static-resources/common_passwords.txt",
        "open_candidate/build_info.txt",
        "open_candidate/vms/distribution/unit_tests/build_distribution_conf.py.in",
        "open_candidate/libs/nx_utils/static-resources/common_passwords.txt",
    },
    # go.mod and go.sum are auto-generated, so they do not need to be checked.
    excluded_file_name_patterns={
        "go.mod", "go.sum", "*.json", "*.json.in", "*.pyc", "*.bmp", "*.gif", "*.mkv", "*.avi",
        "*.png", "*.jpg", "*.jpeg", "*.svg", "*.ui", "*.ts", "*.rc", "qmldir", "control.template",
        "*.wxs", "*.wxl", "*.wxi", "*.xml", "*.conf", "*.conf.in", "*.desktop", "*.plist", "*.def",
        "*.profile", "*.vcproj", "*.vcxproj.user", "_nx_submodule", "*.natvis", "*.cfg", "*.frag",
        "*.vert", "*.pyproj", "*.pem", ".keep", ".gitignore", "*.json.template",
    },
)
