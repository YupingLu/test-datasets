import glob
import json
import os
import pathlib
import click

import rdg_datasets
from libuprev import color
from libuprev.uprev_config import Config


# Try to uprev the rdg using the available methods in priority order
# Returns path to upreved rdg
def try_uprev(config: Config, rdg: str, storage_format_version: int, uprev_methods: dict) -> pathlib.Path:
    # Uprev Method Priority Order:
    # 1) Import
    # 2) Generate
    # 3) Migrate
    # Definitions of these three methods can be found in the repos root README.md

    method = ""
    if uprev_methods.get(rdg_datasets.import_method, None) != None:
        method = rdg_datasets.import_method
        method_handle = uprev_methods.get(rdg_datasets.import_method, None)

    elif uprev_methods.get(rdg_datasets.generate_method, None):
        method = rdg_datasets.generate_method
        method_handle = uprev_methods.get(rdg_datasets.generate_method, None)

    elif uprev_methods.get(rdg_datasets.migrate_method, None):
        method = rdg_datasets.migrate_method
        method_handle = uprev_methods.get(rdg_datasets.migrate_method, None)
    else:
        raise RuntimeError("no valid uprev method for rdg {}, available uprev methods {}".format(rdg, uprev_methods))

    # print("Upreving rdg {}, using method [{}] found at [{}]".format(rdg, method, method_handle))
    return method_handle.uprev(config, storage_format_version)


def validate_version(rdg: str, storage_format_version: int, rdg_dir: pathlib.Path):

    if not rdg_dir.is_dir():
        raise RuntimeError("rdg {} is not present at {}".format(rdg, rdg_dir))

    globs = glob.glob(str(rdg_dir) + "/part_vers00000000000000000001*")
    if len(globs) == 0:
        raise RuntimeError("Failed to locate any part headers for rdg {}.".format(rdg))

    # arbitrarily choose the first one
    part_header_path = pathlib.Path(globs[0])
    if not part_header_path.is_file():
        raise RuntimeError("Failed to locate a valid part header for rdg {}. Found globs : {}".format(rdg, globs))

    with open(part_header_path) as part_header:
        data = json.load(part_header)
        written_version = data.get("kg.v1.storage_format_version", None)
        if written_version == None:
            raise RuntimeError(
                "rdg does not have storage_format_version in its part header. This is expected if this is a storage_format_version=1 rdg"
            )

        if written_version != storage_format_version:
            raise RuntimeError(
                "Written storage_format_version {} does not match expected storage_format_version {}".format(
                    written_version, storage_format_version
                )
            )


@click.group()
def cli():
    """
    tooling to uprev the test dataset rdgs to the latest storage_format_version

    to uprev all rdgs:
    uprev all --storage_format_version=3 --build_dir="/home/user/katana/build"

    to validate that all rdgs have a specific storage_format_version:
    uprev validate --storage_format_version=3

    either can be passed the --continue_on_failure flag to skip over failures for individual rdgs
    """


@cli.command(name="all")
@click.option("--storage_format_version", type=int, required=True, help="storage_format_version to uprev rdgs to")
@click.option("--build_dir", type=str, required=True, help="katana build directory")
@click.option(
    "--continue_on_failure", default=False, is_flag=True, help="Attempt to continue after exception", show_default=True
)
def cli_all(storage_format_version: int, build_dir: str, continue_on_failure: bool):
    config = Config()

    config.build_dir = pathlib.Path(build_dir)

    # mapping from the rdg that failed to the error received
    failed = {}
    # list of rdgs that must be manually upreved
    must_manually_uprev = []
    # mapping from the rdg that was successfully upreved, to its location
    uprev_success = {}

    for rdg, uprev_methods in rdg_datasets.available_uprev_methods().items():
        if len(uprev_methods) == 0:
            must_manually_uprev.append(rdg)
            continue

        try:
            uprev_success[rdg] = try_uprev(config, rdg, storage_format_version, uprev_methods)
            validate_version(rdg, storage_format_version, uprev_success[rdg])
        except Exception as e:
            if not continue_on_failure:
                raise
            else:
                failed[rdg] = e.args

    if len(uprev_success) > 0:
        color.print_ok(
            "******************** Successfully upreved {} rdgs ********************".format(len(uprev_success))
        )
        for rdg, path in uprev_success.items():
            print("\t {} at {}".format(rdg, path))
        print()

    if continue_on_failure and len(failed) > 0:
        color.print_error(
            "******************** Failed while trying to uprev the following {} rdgs ********************".format(
                len(failed)
            )
        )
        for rdg, reason in failed.items():
            print("\t {} : {}".format(rdg, reason))
        print()

    if len(must_manually_uprev) > 0:
        color.print_warn(
            "******************** Must manually uprev the following {} rdgs ********************".format(
                len(must_manually_uprev)
            )
        )
        color.print_warn("see the README file in the rdgs directory for manual uprev instructions")
        for rdg in must_manually_uprev:
            print("\t {1} at {0}/{1}/".format(rdg_datasets.rdg_dataset_dir, rdg))
        print()


@cli.command(name="validate")
@click.option("--storage_format_version", type=int, required=True, help="storage_format_version to check")
@click.option(
    "--continue_on_failure", default=False, is_flag=True, help="Attempt to continue after exception", show_default=True
)
def cli_validate(storage_format_version: int, continue_on_failure: bool):

    # mapping of the rdgs which were successfully validated, to its location
    validated_rdgs = {}
    # mapping from the rdg that failed to the error received
    failed = {}

    rdgs = rdg_datasets.available_rdgs()

    rdg_datasets_path = pathlib.Path(rdg_datasets.rdg_dataset_dir)
    for rdg in rdgs:
        rdg_dir = rdg_datasets_path / rdg
        rdg_dir = rdg_dir / "storage_format_version_{}".format(storage_format_version)
        try:
            validate_version(rdg, storage_format_version, rdg_dir)
            validated_rdgs[rdg] = rdg_dir
        except Exception as e:
            if not continue_on_failure:
                raise
            else:
                failed[rdg] = e.args

    if len(validated_rdgs) > 0:
        color.print_ok(
            "******************** Successfully validated {} rdgs ********************".format(len(validated_rdgs))
        )
        for rdg, path in validated_rdgs.items():
            print("\t {} at {}".format(rdg, path))
        print()

    if continue_on_failure and len(failed) > 0:
        color.print_error(
            "******************** Failed to validate the following {} rdgs ********************".format(len(failed))
        )
        for rdg, reason in failed.items():
            print("\t {} : {}".format(rdg, reason))
        print()

    if len(validated_rdgs) != len(rdgs) and len(failed) == 0:
        color.print_error("ERROR: not all rdgs were validated, but not failures were observed")
        color.print_error("expected to validate: {}".format(rdgs))
        color.print_error("but only validated: {}".format(validated_rdgs))


if __name__ == "__main__":
    cli.main(prog_name="uprev")
