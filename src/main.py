# Copyright (c) 2021, texture·design.
import glob
import os
import json
import pathlib
import multiprocessing

import random
import imageio

import numpy
import torch
import torch.nn.functional as F

from pathlib import Path

import toml
import click

from material import Material, MaterialScanner
from library import MaterialLibrary

from compute_displacement import normalize

class MaterialExporter:
    def __init__(
        self,
        datasets: list,
        export_path: pathlib.Path,
        export_resolution: tuple[int],
        export_format: str,
    ):
        self.datasets = datasets
        self.export_path = export_path
        self.export_resolution = export_resolution
        self.export_format = export_format
        self.ignore_default = ["\.DS_Store", "Thumbs\.db", "(?i:preview)", "(?i:thumb)"]

    def export_material(self, args):
        (filenames, info) = args

        mat = Material(filenames, **info)
        res = max(self.export_resolution) // 1024

        export_path = self.export_path / mat.hash / f"{res}K-{self.export_format.upper()}"
        if os.path.exists(export_path):
            return mat

        try:
            mat.load()
        except FileNotFoundError:
            return None

        diffuse_size = mat.images["diffuse"].size
        if diffuse_size != self.export_resolution:
            return None

        mat.export(export_path, format=self.export_format.lower())
        mat.unload()
        material = mat.hash
        # Normalize displacement maps
        normalize(str(export_path), material)
        return mat


    def find_all_materials(self):
        for config in self.datasets:
            clib, cscan = config["library"], config["scanner"]
            scanner = MaterialScanner(
                exclude=self.ignore_default + cscan.get("ignore", []),
                allow_variations=False,
                allow_remaining=cscan.get("allow_remaining", []),
            )

            library = MaterialLibrary(
                clib["name"], clib["glob"], excludes=clib.get("exclude", [])
            )
            for path, info in library.find_directories():
                try:
                    for filenames in scanner.from_directory(path):
                        yield filenames, info

                except FileNotFoundError as exc:
                    print("WARNING:", path, exc)
                    continue


@click.command()
@click.argument("library-configs", nargs=-1)
@click.option("--export-path", type=pathlib.Path, default="cache")
@click.option("--export-resolution", type=tuple[int], default=(4096, 4096))
@click.option("--export-format", type=str, default="JPG")

def main(library_configs, export_path, export_resolution, export_format):
    libraries = [toml.load(cfg) for cfg in library_configs]

    pool = multiprocessing.Pool(1)
    exporter = MaterialExporter(
        libraries, export_path, export_resolution, export_format
    )

    index = []
    for material in pool.imap_unordered(
        exporter.export_material, exporter.find_all_materials()
    ):
        if material is None:
            continue

        index.append(
            dict(uuid=material.hash, url=material.url, tags=list(material.tags),)
        )

    json.dump(index, open(f"{export_path}/index.json", "w"))
    print(f"Exported {len(index)} materials to `{export_path}` directory.")

    # exporter.normalize_displacement()

if __name__ == "__main__":
    main()
