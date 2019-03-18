#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""point2grid
Converts a set of ground-based observations into a gridded dataset. It
has been designed to work with the raw files of climatological
observations from the Climatologic Database of the National
Meteorological Service of Mexico (SMN).
"""
__author__ = 'Roberto A. Real-Rangel (Institute of Engineering UNAM)'
__license__ = 'GNU General Public License version 3'

import numpy as np
import pandas as pd

from scipy.spatial import distance_matrix
import xarray as xr

import lib.data_manager as dmgr
import lib.spatial_analysis as span

# Load initial configurations.
config = dmgr.Configurations('config.toml')

# Filter datasets within the region of interest.
inregion_vmap, inregion_attrs = span.filter_stations(
        catalog_vmap=config.catalog_vmap,
        study_region=config.study_region,
        buffer_dist=80000)

# Generate a dataframe with the data of all filtered datasets.
inregion_data = dmgr.gen_database(
        catalog_dir=config.catalog_dir,
        inregion_attrs=inregion_attrs,
        variable=config.variable,
        qc=config.qc)

# Interpolate the daily data.
inregion_attrs = dmgr.get_elevation(
        catalog_dir=config.catalog_dir,
        inregion_attrs=inregion_attrs)
years = range(
        inregion_data.index[0].year,
        inregion_data.index[-1].year + 1)

for yy, year in enumerate(years):
    aux = []
    dates = inregion_data.loc[str(year)].index

    for date in dates:
        grid_cells, basin_grid = span.inregion_cells(
                study_region=config.study_region,
                res=config.grid_spec['res'],
                nodata=config.grid_spec['nodata'])
        grid_cells = span.retrieve_elevation(
                input_rmap=config.dem,
                coordinates=grid_cells,
                res=config.grid_spec['res'],
                nodata=config.grid_spec['nodata'])

        # Get available data for the given date.
        indate_values = inregion_data.xs(date).dropna()

        if len(indate_values) > 2:
            # Interpolate values only if more than two stations were available.
            # Generate a distance matrix for the grid and the data.
            stations_points = [
                    (inregion_attrs[i]['East'], inregion_attrs[i]['North'],
                     inregion_attrs[i]['Elevation'])
                    for i in indate_values.keys()]
            distmat = pd.DataFrame(
                    distance_matrix(x=grid_cells, y=stations_points),
                    columns=indate_values.index)

            # Apply the IDW interpolation.
            for c, cell in enumerate(grid_cells):
                x_index = np.where(basin_grid.x == cell[0])[0]
                y_index = np.where(basin_grid.y == cell[1])[0]
                cell_distances = distmat.iloc[c]
                distances = cell_distances[
                        (cell_distances < config.max_distance)]

                if len(distances) > 2:
                    basin_grid.values[y_index, x_index] = span.interpolate_idw(
                            distances=distances,
                            values=indate_values,
                            power=2)

        aux.append(np.expand_dims(basin_grid.values, axis=0))

    if len(aux) > 1:
        if np.sum([np.sum(np.isfinite(i)) for i in aux]) > 0:
            # Generates an output only if more than one of the day has data.
            output_dataarray = xr.DataArray(
                    data=np.vstack(aux),
                    coords={'time': dates,
                            'north': basin_grid.y,
                            'east': basin_grid.x},
                    dims=['time', 'north', 'east'])

            # Export basin_grid datasets.
            output_file = config.out_directory + '/' + (str(year) + '.nc4')
            output_dataarray.to_netcdf(
                    path=output_file,
                    mode='w',
                    format='NETCDF4')
    dmgr.progress_bar(current=(yy + 1), total=len(years), message=(
            "- Interpolating daily records and exporting datasets"))
