# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module
# pylint: disable=too-many-lines
# pylint: disable=useless-return
# pylint: disable=too-few-public-methods
# pylint: disable=relative-beyond-top-level

# /***************************************************************************
# simplify_algorithm.py
# ----------
# Date                 : April 2021
# copyright            : (C) 2020 by Natural Resources Canada
# email                : daniel.pilon@canada.ca
#
#  ***************************************************************************/
#
# /***************************************************************************
#  *                                                                         *
#  *   This program is free software; you can redistribute it and/or modify  *
#  *   it under the terms of the GNU General Public License as published by  *
#  *   the Free Software Foundation; either version 2 of the License, or     *
#  *   (at your option) any later version.                                   *
#  *                                                                         *
#  ***************************************************************************/

"""
QGIS Plugin for Simplification (Douglas-Peucker algorithm)
"""

import os
import inspect
import json
import shutil
import uuid
import uuid
import zipfile
from typing import List
from datetime import datetime
from dataclasses import dataclass
import tempfile
from pathlib import (Path, PurePath)
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.core import (Qgis, QgsProcessing, QgsProcessingAlgorithm, QgsProcessingParameterDistance,
                       QgsProcessingParameterFeatureSource, QgsProcessingParameterFeatureSink,
                       QgsFeatureSink, QgsFeatureRequest, QgsLineString, QgsWkbTypes, QgsGeometry,
                       QgsProcessingException, QgsProcessingParameterMultipleLayers, QgsMapLayer,
                       QgsVectorLayerExporter, QgsVectorFileWriter, QgsProject, QgsProcessingParameterEnum,
                       QgsProcessingParameterString, QgsProcessingParameterFolderDestination,
                       QgsMapLayerStyleManager, QgsReadWriteContext, QgsDataSourceUri,  QgsDataProvider,
                       QgsProviderRegistry)
import processing
from .geo_sim_util import Epsilon, GsCollection, GeoSimUtil, GsFeature, ProgressBar

@dataclass
class ControlFile:
    """"
    Declare the fields in the control control file
    """
    department: str = None
    download_info_id: str = None
    email: str = None
    metadata_uuid: str = None
    qgis_server_id: str = None
    download_package_name: str = ''
    core_subject_term: str = ''
    csz_collection_linked: str = ''
    in_project_filename: str = None
    language: str = None
    service_schema_name: str = None
    gpkg_file_name: str = None        # Name of Geopakage containing the vector layers
    control_file_dir: str = None      # Name of temporary directory
    control_file_name: str = None     # Name of the control file
    control_file_zip: str = None      # Name of the zip file
    write_project: str = None
    json_document: str = None         # Name of the JSON document
    dst_qgs_project_name: str = None  # Name of the output QGIS project file
    layers: object = None             # List of the list to process


class UserMessageException(Exception):
    """Exception raised when a message (likely an error message) needs to be sent to the User."""
    pass


class SimplifyAlgorithm(QgsProcessingAlgorithm):
    """Main class defining the Simplify algorithm as a QGIS processing algorithm.
    """

    def tr(self, string):  # pylint: disable=no-self-use
        """Returns a translatable string with the self.tr() function.
        """
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):  # pylint: disable=no-self-use
        """Returns a new copy of the algorithm.
        """
        return SimplifyAlgorithm()

    def name(self):  # pylint: disable=no-self-use
        """Returns the unique algorithm name.
        """
        return 'simplify'

    def displayName(self):  # pylint: disable=no-self-use
        """Returns the translated algorithm name.
        """
        return self.tr('Publish Vector Layers')

    def group(self):
        """Returns the name of the group this algorithm belongs to.
        """
        return self.tr(self.groupId())

    def groupId(self):  # pylint: disable=no-self-use
        """Returns the unique ID of the group this algorithm belongs to.
        """
        return ''

    def flags(self):

        return super().flags() | QgsProcessingAlgorithm.FlagNoThreading

    def shortHelpString(self):
        """Returns a localised short help string for the algorithm.
        """
        help_str = """
    Simplify is a geospatial simplification (generalization) tool for lines and polygons. Simplify \
    implements an improved version of the classic Douglas-Peucker algorithm with spatial constraints \
    validation during geometry simplification.  Simplify will preserve the following topological relationships:  \
    Simplicity (within the geometry), Intersection (with other geometries) and Sidedness (with other geometries).

    <b>Usage</b>
    <u>Input layer</u> : Any LineString or Polygon layer.  Multi geometry are transformed into single part geometry.
    <u>Tolerance</u>: Tolerance used for line simplification.
    <u>Simplified</u> : Output layer of the algorithm.

    <b>Rule of thumb for the diameter tolerance</b>
    Simplify (Douglas-Peucker) is an excellent tool to remove vertices on features with high vertex densities \
    while preserving a maximum of details within the geometries.  Try it with small tolerance value and then use \
    Reduce Bend to generalize features (generalization is needed).

    """

        return self.tr(help_str)

    def icon(self):  # pylint: disable=no-self-use
        """Define the logo of the algorithm.
        """

        cmd_folder = os.path.split(inspect.getfile(inspect.currentframe()))[0]
        icon = QIcon(os.path.join(os.path.join(cmd_folder, 'logo.png')))
        return icon

    def initAlgorithm(self, config=None):  # pylint: disable=unused-argument
        """Define the inputs and outputs of the algorithm.
        """

        self.addParameter(QgsProcessingParameterMultipleLayers(
            name='LAYERS',
            description=self.tr("Select input vector layer(s)"),
            layerType=QgsProcessing.TypeVectorAnyGeometry))

        lst_department = ['eccc',
                          'nrcan']
        self.addParameter(QgsProcessingParameterEnum(
            name='DEPARTMENT',
            description=self.tr("Select your department"),
            options=lst_department,
            defaultValue="nrcan",
            usesStaticStrings=True,
            allowMultiple=False))

        lst_download_info_id = ["DDR_DOWNLOAD1"]
        self.addParameter(QgsProcessingParameterEnum(
            name='DOWNLOAD_INFO_ID',
            description=self.tr("Select your download info ID"),
            options=lst_download_info_id,
            defaultValue=lst_download_info_id[0],
            usesStaticStrings=True,
            allowMultiple=False))

        self.addParameter(QgsProcessingParameterString(
                name="EMAIL",
                defaultValue="daniel.pilon@nrcan-rncan.gc.ca",
                description=self.tr('Enter your email address')))

        lst_qgs_server_id = ['DDR_QGS1']
        self.addParameter(QgsProcessingParameterEnum(
            name='QGS_SERVER_ID',
            description=self.tr('Select the QGIS server'),
            options=lst_qgs_server_id,
            defaultValue=lst_qgs_server_id[0],
            usesStaticStrings=True,
            allowMultiple=False))

        lst_language = ['English', 'French']
        self.addParameter(QgsProcessingParameterEnum(
            name='LANGUAGE',
            description=self.tr('Select service language'),
            options=lst_language,
            usesStaticStrings=True,
            allowMultiple=False))

        self.addParameter(QgsProcessingParameterEnum(
            name='SERVICE_SCHEMA_NAME',
            description=self.tr("Select the schema name to publish"),
            options=lst_department,
            usesStaticStrings=True,
            defaultValue="nrcan",
            allowMultiple=False))

        lst_flag = ['Yes', 'No']
        self.addParameter(QgsProcessingParameterEnum(
            name='WRITE_PROJECT',
            description=self.tr('Write QGIS project file before publishing the service'),
            options=lst_flag,
            defaultValue=lst_flag[0],
            usesStaticStrings=True,
            allowMultiple=False))


    @staticmethod
    def get_date_time():
        """Extract the current date and time """

        now = datetime.now()  # current date and time
        date_time = now.strftime("%Y-%m-%d %H:%M:%S")

        return date_time

    def read_parameters(self, ctl_file, parameters, context, feedback):
        """Reads the different parameters in the form and stores the content in the data structure"""

        ctl_file.department = self.parameterAsString(parameters, 'DEPARTMENT', context)
        ctl_file.download_info_id = self.parameterAsString(parameters, 'DOWNLOAD_INFO_ID', context)
        ctl_file.email = self.parameterAsString(parameters, 'EMAIL', context)
        ctl_file.qgs_server_id = self.parameterAsString(parameters, 'QGS_SERVER_ID', context)
        ctl_file.language = self.parameterAsString(parameters, 'LANGUAGE', context)
        ctl_file.service_schema_name = self.parameterAsString(parameters, 'SERVICE_SCHEMA_NAME', context)
        ctl_file.write_project = self.parameterAsString(parameters, 'WRITE_PROJECT', context)
        ctl_file.layers = self.parameterAsLayerList(parameters, 'LAYERS', context)

        return

    def validate_parameters(self, ctl_file, parameters, context, feedback):
        """Validate the the parameters"""

        # Validate that there is no duplicate layer name
        tmp_layers = []
        for layer in ctl_file.layers:
            tmp_layers.append(layer.name())

        for tmp_layer in tmp_layers:
            if tmp_layers.count(tmp_layer) > 1:
                # Layer is not unique
                raise UserMessageException(f"Remove duplicate layer: {tmp_layer} in QGS project file")

    def remove_unselected_layers(self, ctl_file, parameters, context, feedback):
        """Remove from the .qgs project file all the unselected layers (only keep selected layers)"""

        # Extract the name of the selected layers
        lst_layer_name = []
        for layer in ctl_file.layers:
            lst_layer_name.append(layer.name())

        qgs_project = QgsProject.instance()
        for layer in qgs_project.mapLayers().values():
            if lst_layer_name.count(layer.name()) == 0:
                # The layer is not selected and mus be removed
                file = True
                str_date_time = SimplifyAlgorithm.get_date_time()
                feedback.pushInfo(f"{str_date_time} - INFO: Removing layer: {layer.name()} from the project file")
                qgs_project.removeMapLayer(layer.id())

        if qgs_project.isDirty():
            # File needs to be saved
            qgs_project_file_name = qgs_project.fileName()
            qgs_project.write(qgs_project_file_name)

        return

    def copy_qgis_project_file(self, ctl_file, parameters, context, feedback):
        """Creates a copy of the QGIS project file"""

        qgs_project = QgsProject.instance()
        str_date_time = SimplifyAlgorithm.get_date_time()
        ctl_file.src_qgs_project_name = qgs_project.fileName()  # Extract the name of the QGS project file

        # Validate that a file QGS project file is present
        if ctl_file.src_qgs_project_name is None:
            raise UserMessageException("A QGS project file is not loaded...")

        # Validate the extension of the QGS project file
        extension = PurePath(ctl_file.src_qgs_project_name).suffix
        if extension != ".qgs":
            raise UserMessageException("Error the QGIS project file extension must be '.qgs' not: '{0}".format(extension))

        # Validate that the project is saved before the processing
        if qgs_project.isDirty():
            raise UserMessageException("Error the QGIS projec file must be saved before starting the publication")

        # Create temporary directory
        ctl_file.control_file_dir = tempfile.mkdtemp(prefix='qgis_')
        feedback.pushInfo(f"{str_date_time} - INFO: Temporary directory created: {ctl_file.control_file_dir}")

        # Copy the QGIS project file (.qgs) in the temporary directory
        ctl_file.in_project_filename = Path(ctl_file.src_qgs_project_name).name
        dst_qgs_project_name = os.path.join(ctl_file.control_file_dir, ctl_file.in_project_filename)

        # Save as... under the new name in the temporary directory
        qgs_project.write(dst_qgs_project_name)
######        shutil.copy(ctl_file.src_qgs_project_name, dst_qgs_project_name)
        feedback.pushInfo(f"{str_date_time} - INFO: QGIS project file save as: {dst_qgs_project_name}")

    def copy_layer_gpkg(self, ctl_file, parameters, context, feedback):
        """Copy the selected layers in GeoPackage file"""

        ctl_file.gpkg_file_name = os.path.join(ctl_file.control_file_dir, "qgis_vector_layers.gpkg")
        qgs_project = QgsProject.instance()

        total = len(ctl_file.layers)  # Total number of vector layer to process
        # Loop over each selected layers
        for i, src_layer in enumerate(qgs_project.mapLayers().values()):
            transform_context = QgsProject.instance().transformContext()
            if src_layer.isSpatial():
                # Only process Spatial layers
                if src_layer.type() == QgsMapLayer.VectorLayer:
                    # Only select vector layer
                    options = QgsVectorFileWriter.SaveVectorOptions()
                    options.layerName = src_layer.name()
                    options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer if Path(
                        ctl_file.gpkg_file_name).exists() else QgsVectorFileWriter.CreateOrOverwriteFile
                    options.feedback = None
                    str_date_time = SimplifyAlgorithm.get_date_time()
                    str_output = f"{str_date_time} - INFO: Copying layer: {src_layer.name()} ({str(i+1)}/{str(total)})"
                    feedback.pushInfo(str_output)

                    error, err1, err2, err3 = QgsVectorFileWriter.writeAsVectorFormatV3(layer = src_layer,
                                                  fileName =ctl_file.gpkg_file_name,
                                                  transformContext = transform_context,
                                                  options = options)

                else:
                    feedback.pushInfo(f"{str_date_time} - WARNING: Layer: {0} is not vector ==> Not transfered")
            else:
                feedback.pushInfo(f"{str_date_time} - WARNING: Layer: {0} is not spatial ==> transfered")

        # Use the newly created GPKG file to set the data source of the QGIS project file
        provider_options = QgsDataProvider.ProviderOptions()
        provider_options.transformContext = qgs_project.transformContext()
        # Loop over each layer
        for src_layer in qgs_project.mapLayers().values():
            layer_name = src_layer.name()
            uri = QgsProviderRegistry.instance().encodeUri('ogr',
                                                           {'path': ctl_file.gpkg_file_name, 'layerName': layer_name})
            src_layer.setDataSource(uri, layer_name, "ogr", provider_options)

        dst_qgs_project_name = os.path.join(ctl_file.control_file_dir, ctl_file.in_project_filename)
        qgs_project.write(dst_qgs_project_name)

    def create_json_control_file(self, ctl_file, parameters, context, feedback):
        """Creation and writing of the JSON control file"""

        # Creation of the JSON control file
        ctl_file.metadata_uuid = str(uuid.uuid4())
        json_control_file = {
            "generic_parameters": {
                "department": ctl_file.department,
                "download_info_id": ctl_file.download_info_id,
                "email": ctl_file.email,
                "metadata_uuid": ctl_file.metadata_uuid,
                "qgis_server_id": ctl_file.qgs_server_id,
                "download_package_name": ctl_file.download_package_name,
                "core_subject_term": ctl_file.core_subject_term,
                "czs_collection_linked": ctl_file.csz_collection_linked
            },
            "service_parameters": [
                {
                    "in_project_filename": ctl_file.in_project_filename,
                    "language": ctl_file.language,
                    "service_schema_name": ctl_file.service_schema_name
                }
            ]
        }

        # Serialize the JSON
        json_object = json.dumps(json_control_file, indent=4)

        # Write the JSON document
        ctl_file.control_file_name = os.path.join(ctl_file.control_file_dir, "ControlFile.json")
        with open(ctl_file.control_file_name, "w") as outfile:
            outfile.write(json_object)

        str_date_time = SimplifyAlgorithm.get_date_time()
        feedback.pushInfo(f"{str_date_time} - INFO: Creation of the JSON control file: {ctl_file.control_file_name}")

        return

    def create_zip_file(self, ctl_file, parameters, context, feedback):
        """Create the zip file"""

        # Change working directory to the temporary directory
        current_dir = os.getcwd()  # Save current directory
        os.chdir(ctl_file.control_file_dir)

        # Create the zip file
        lst_file_to_zip = [Path(ctl_file.control_file_name).name,
                           Path(ctl_file.gpkg_file_name).name,
                           Path(ctl_file.in_project_filename).name]
        zip_file_name = os.path.join(ctl_file.control_file_dir, "ddr_publish.zip")
        str_date_time = SimplifyAlgorithm.get_date_time()
        feedback.pushInfo(f"{str_date_time} - INFO: Creating the zip file: {zip_file_name}")
        with zipfile.ZipFile(zip_file_name, mode="w") as archive:
            for file_to_zip in lst_file_to_zip:
                archive.write(file_to_zip)

        # Reset the current directory
        os.chdir(current_dir)

    def restore_original_project_file(self, ctl_file, parameters, context, feedback):
        """Restore the original project file"""

        qgs_project = QgsProject.instance()

        # Close the current project file file
        #qgs_project.clear()

        # Reopen the original project file
        str_date_time = SimplifyAlgorithm.get_date_time()
        feedback.pushInfo(f"{str_date_time} - INFO: Restorinng original project file (.qgs): {ctl_file.src_qgs_project_name}")
#        qgs_project.clear()
#        qgs_project = QgsProject.instance()
#        qgs_project.read(ctl_file.src_qgs_project_name)
#        print (qgs_project)
#        qgs_project = QgsProject.instance()
        qgs_project.read(ctl_file.src_qgs_project_name)


    def processAlgorithm(self, parameters, context, feedback):
        """Main method that extract parameters and call Simplify algorithm.
        """

#        from qgis import processing
#        import web_pdb
#        web_pdb.set_trace()

##        qgs_project = QgsProject.instance()
##        for layer in qgs_project.mapLayers().values():
##            print (layer.name())
##            print(layer.id())
##            print(layer.source())

##        file_name_gpkg = 'C:/DATA/test/test_final55123.gpkg'
##        result = processing.run("native:package", {'LAYERS': ['C:/DATA/test/test_final2.gpkg|layername=coco',
##                                                              'C:/DATA/test/test_final2.gpkg|layername=nodatanodata2'],
##                                                   'OUTPUT':file_name_gpkg,
##                                                   'OVERWRITE':True,
##                                                   'SAVE_STYLES':True,
##                                                   'SAVE_METADATA':True,
##                                                   'SELECTED_FEATURES_ONLY':False,
##                                                   'EXPORT_RELATED_LAYERS':False})
##        print (result)

##        qgs_project = QgsProject.instance()
##        qgs_project.removeAllMapLayers()

##        provider_options = QgsDataProvider.ProviderOptions()
##        provider_options.transformContext = qgs_project.transformContext()
##        for src_layer in qgs_project.mapLayers().values():
##            uri1 = src_layer.customProperty('original_uri')
##            uri2 = sr_layer = src_layer.source()
###            file_name_gpkg = "C:\\DATA\\test\\fichier_gpkg_"
###            file_name = file_name_gpkg + "_" + src_layer.name() + ".gpkg"
##            uri = QgsProviderRegistry.instance().encodeUri('ogr', {'path': file_name_gpkg, 'layerName': options.layerName})
##            src_layer.setDataSource(uri, src_layer.name(), "ogr", provider_options)

##        dst_qgs_project_name = os.path.join(ctl_file.control_file_dir, ctl_file.in_project_filename)



#        import web_pdb
#        web_pdb.set_trace()

        # Create the control file data structure
        ctl_file = ControlFile()

#        qgs_project = QgsProject.instance()
#        print("Done1")
#        a = Qgis.ProjectReadFlags()
#        a |= QgsProject.FlagDontLoadLayouts
#        a |= QgsProject.ForceReadOnlyLayers


#        print (a)

#        qgs_project.write()
#        for layer in qgs_project.mapLayers().values():
#            print("Done2", layer.name(), layer.id())
#            qgs_project.removeMapLayer(layer.id())
#        print("Done2.5")
#        qgs_project.write()

#        qgs_project.clear()
#        qgs_project = QgsProject.instance()


#        print(qgs_project.write("C:/Users/dpilon/Desktop/old/toto27all.qgs"))
#        qgs_project = QgsProject.instance()
#        print (qgs_project)
#        qgs_project.read('C:/Users/dpilon/Desktop/old/toto272.qgs', a)
###        qgs_project.read('C:\\Users\\dpilon\\Desktop\\old\\toto27.qgs')
#        print("Done3")
#        0 / 0

        # Extract the parameters
        self.read_parameters(ctl_file, parameters, context, feedback)



        # Validate the parameters
        self.validate_parameters(ctl_file, parameters, context, feedback)



        # Copy the QGIS project file (.qgs)
        self.copy_qgis_project_file(ctl_file, parameters, context, feedback)



        # Remove unselected layers from the .qgs project file
        self.remove_unselected_layers(ctl_file, parameters, context, feedback)

        # Copy the selected layers in the GPKG file
        self.copy_layer_gpkg(ctl_file, parameters, context, feedback)

        # Creation of the JSON control file
        self.create_json_control_file(ctl_file, parameters, context, feedback)

        # Creation of the ZIP file
        self.create_zip_file(ctl_file, parameters, context, feedback)

        # Publish the project file to the DDR

        # Restoring original .qgs project file
        self.restore_original_project_file(ctl_file, parameters, context, feedback)



        0/0

        qgs_project = QgsProject.instance()
        qgs_project.write("C:\\Users\\dpilon\\Desktop\\old\\toto27.qgs")
        qgs_project = QgsProject.instance()
        qgs_project.clear()
        qgs_project = QgsProject.instance()
        qgs_project.read("C:\\Users\\dpilon\\Desktop\\old\\toto27.qgs")



#        ctl_file.department = self.parameterAsString(parameters, 'DEPARTMENT', context)
#        ctl_file.download_info_id = self.parameterAsString(parameters, 'DOWNLOAD_INFO_ID', context)
#        ctl_file.email = self.parameterAsString(parameters, 'EMAIL', context)
#        ctl_file.qgs_server_id = self.parameterAsString(parameters, 'QGS_SERVER_ID', context)
#        ctl_file.language = self.parameterAsString(parameters, 'LANGUAGE', context)
#        ctl_file.service_schema_name = self.parameterAsString(parameters, 'SERVICE_SCHEMA_NAME', context)
#        ctl_file.write_project = self.parameterAsString(parameters, 'WRITE_PROJECT', context)
#        layers = self.parameterAsLayerList(parameters, 'LAYERS', context)




#        # Create temporary directory
#        ctl_file.control_file_dir = tempfile.mkdtemp(prefix='qgis_')


#  #      # Extract the QGIS project absolute file path
#        qgs_project = QgsProject().instance()
#        src_qgs_project_name = qgs_project.absoluteFilePath()

        # Save (write) the QGS project if requested
 #       if ctl_file.write_project == "Yes":
 #           qgs_project.writePath(src_qgs_project_name)
 #           feedback.pushInfo("QGS Project file saved: {0}".format(src_qgs_project_name))

        #import web_pdb;
        #web_pdb.set_trace()

#        # Copy the QGIS project file (.qgs) in the temporary directory
#        ctl_file.in_project_filename = Path(src_qgs_project_name).name
#        dst_qgs_project_name = os.path.join(ctl_file.control_file_dir, ctl_file.in_project_filename)
#        shutil.copy(src_qgs_project_name, dst_qgs_project_name)

        # Create the name of the GeoPackage that will contain all the vector layers
        file_name_gpkg = os.path.join(ctl_file.control_file_dir, "qgis_vector_layers.gpkg")

        # Set progress bar to 1%
        feedback.setProgress(1)

        # Export the selected vector layers into a GeoPackage
        total = len(layers)
        for i, layer in enumerate(layers):


            transform_context = QgsProject.instance().transformContext()
            if layer.isSpatial():
                # Only select Spatial layers
                if layer.type() == QgsMapLayer.VectorLayer:
                    # Only select vector layer
                    options = QgsVectorFileWriter.SaveVectorOptions()
                    options.layerName = layer.name()
                    options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer if Path(
                         file_name_gpkg).exists() else QgsVectorFileWriter.CreateOrOverwriteFile
                    options.feedback=None
                    str_output = "Copying layer: {0} ({1}/{2})".format(layer.name(), str(i+1), str(total))
                    feedback.pushInfo(str_output)

                    style = QgsMapLayerStyleManager(layer)
                    current = style.currentStyle()
                    print (style.mapLayerStyles)
                    print("*******", current)


#                    error, err1, err2, err3 = QgsVectorFileWriter.writeAsVectorFormatV3(layer = layer,
#                                                                                     fileName = file_name_gpkg,
#                                                                                     transformContext = transform_context,
#                                                                                     options = options)

                    #import web_pdb
                    #web_pdb.set_trace()
                    #l0 = qgs_project.mapLayersByName('coco')
                    #layer0 = qgs_project.mapLayersByName('coco')[0]
                    #        layer1 = qgs_project.mapLayersByName('nodatanodata2')[0]
                    output_path = "C:\\DATA\\test\\test3.gpkg"

                    options = {}
                    options['update'] = True
                    options['driverName'] = 'GPKG'
                    options['layerName'] = layer.name()
                    #        err = QgsVectorLayerExporter.exportLayer(lyr, tmpfile, "ogr", lyr.crs(), False, options)
                    a, b = QgsVectorLayerExporter.exportLayer(
                        layer=layer,
                        uri=output_path,
                        providerKey='ogr',
                        onlySelected=False,
                        options=options,
                        destCRS=layer.crs())
                    print(a, b)

                    layer.setDataSource(output_path, layer.name(), "ogr")
                    qgs_project.removeMapLayer(layer.id())





                    feedback.setProgress(int(((i+1)/total)*100)-1)

#                    import web_pdb;
#                    web_pdb.set_trace()
#                    from PyQt5.QtXml import QDomDocument
#                    error = ""
#                    doc = QDomDocument()
#                    node = doc.createElement("symbology")
#                    doc.appendChild(node)
#                    [count, style_ids, style_names, style_descs, error] = layer.listStylesInDatabase()
#                    layer.writeSymbology(node, doc, error, QgsReadWriteContext())
#
#                    qgs_project = QgsProject.instance()
#                    qgs_project.removeMapLayer(layer.id())



                else:
                    feedback.pushInfo("Layer: {0} is not vector; it will not be transfered".format(layer.name()))
            else:
                feedback.pushInfo("Layer: {0} is not spatial; it will not be transfered".format(layer.name()))




        # Creation of the JSON control file
        feedback.pushInfo("Creating and serializing the JSON Control file")
        ctl_file.metadata_uuid = str(uuid.uuid4())
        json_control_file = {
            "generic_parameters": {
                "department": ctl_file.department,
                "download_info_id": ctl_file.download_info_id,
                "email": ctl_file.email,
                "metadata_uuid": ctl_file.metadata_uuid,
                "qgis_server_id": ctl_file.qgs_server_id,
                "download_package_name": ctl_file.download_package_name,
                "core_subject_term": ctl_file.core_subject_term,
                "czs_collection_linked": ctl_file.csz_collection_linked
            },
            "service_parameters": [
                {
                    "in_project_filename": ctl_file.in_project_filename,
                    "language": ctl_file.language,
                    "service_schema_name": ctl_file.service_schema_name
                }
            ]
        }

        # Serialize the JSON
        json_object = json.dumps(json_control_file, indent=4)

        # Write the JSON document
        control_file_name = os.path.join(ctl_file.control_file_dir, "ControlFile.json")
        with open(control_file_name, "w") as outfile:
            outfile.write(json_object)


        working_directory = os.getcwd()
        os.chdir(ctl_file.control_file_dir)
        working_directory1 = os.getcwd()
        os.chdir(working_directory)
        working_directory = os.getcwd()


        # Change working directory to the temporary directory
        current_dir = os.getcwd()  # Save current directory
        os.chdir(ctl_file.control_file_dir)

        # Create the zip file
        lst_file_to_zip = [Path(control_file_name).name,
                           Path(file_name_gpkg).name,
                           Path(ctl_file.in_project_filename).name]
        zip_file_name = os.path.join(ctl_file.control_file_dir,  "ddr_publish.zip")
        feedback.pushInfo("Creating the zip file: {0}".format(zip_file_name))
        with zipfile.ZipFile(zip_file_name, mode="w") as archive:
            for file_to_zip in lst_file_to_zip:
                archive.write(file_to_zip)

        # Reset the current directory
        os.chdir(current_dir)


#        qgs_project.write("C:\\DATA\\test\\test.qgs")
#        layer_coco = qgs_project.mapLayer('coco')
#        qgs_project.removeLayer(layer_coco.id())
#        qgs_project.write("C:\\DATA\\test\\test.qgs")

        import web_pdb
        web_pdb.set_trace()
        l0 = qgs_project.mapLayersByName('coco')
        layer0 = qgs_project.mapLayersByName('coco')[0]
#        layer1 = qgs_project.mapLayersByName('nodatanodata2')[0]
        output_path = "C:\\DATA\\test\\test3.gpkg"

        options = {}
        options['update'] = True
        options['driverName'] = 'GPKG'
        options['layerName'] = 'coco'
#        err = QgsVectorLayerExporter.exportLayer(lyr, tmpfile, "ogr", lyr.crs(), False, options)
        a, b = QgsVectorLayerExporter.exportLayer(
            layer=layer0,
            uri=output_path,
            providerKey='ogr',
            onlySelected=False,
            options=options,
            destCRS=layer.crs())
        print (a,b)

#        options['update'] = True
#        options['driverName'] = 'GPKG'
#        options['layerName'] = 'coco2'
#        #        err = QgsVectorLayerExporter.exportLayer(lyr, tmpfile, "ogr", lyr.crs(), False, options)
#        a, b = QgsVectorLayerExporter.exportLayer(
#            layer=layer0,
#            uri=output_path,
#            providerKey='ogr',
#            onlySelected=False,
#            options=options,
#            destCRS=layer.crs())
#        print(a, b)




        for layer_l in qgs_project.mapLayers().values():
            layer = layer_l
            break
#        uri = QgsDataSourceUri()
#        uri.setDatabase(output_path)
#        layer.setDatasource(output_path, layer.name(), )
#        uri.setDataSource('coco',
#                          layer.name(),
#                          'geom' )

#        import web_pdb
#        web_pdb.set_trace()
#        provider_options = QgsDataProvider.ProviderOptions()
        # Use project's transform context
#        provider_options.transformContext = QgsProject.instance().transformContext()
        layer.setDataSource(output_path, layer.name(), "ogr")
        qgs_project.write("C:\\DATA\\test\\test_out.qgs")

#
#                    opts = {}
#                    opts['append'] = False
#                    opts['update'] = True
#                    opts['overwrite'] = True
#                    error, errMsg = QgsVectorLayerExporter.exportLayer(layer, uri, 'ogr', layer.crs(),
#                                                                       False, options=opts)
#                    print (error, errMsg)
#                    if error != QgsVectorLayerExporter.NoError:
#                        raise IOError(u"Failed to add layer to database '{}': error {}".format(dbname, errMsg))
#
#
#                #                    exporter = QgsVectorLayerExporter(uri=uri,
#                                                      provider='ogr',
#                                                      fields=layer.fields(),
#                                                      crr=layer.crs(),
#                                                      overwite=True,
#                                                      geometryType=layer.geometryType())
#                    exporter.addFeatures(layer.getFeatures())
#
#                else:
#                    print ("Layer is not vector")
#            else:
#                print ("Layer is not Spatial data")#
#
#
#            ret_code = QgsVectorLayerExporter.exportLayer(
#                           layer=layer,
#                           uri="c:\\DATA\\test\\t.gpkg",
#                           providerKey='ogr',
#                           destCRS=layer.crs(),
#                           onlySelected=False)
#            print (ret_code)
#            uri = "c:\\DATA\\test\\t.gpkg"
#            print("layer Geom: ", layer.wkbType())
#            exporter = QgsVectorLayerExporter(uri, ogr, fields=layer.fields(), crs=layer.crs(),
#                                              overwrite=True,
#                                              geometryType=QgsWkbTypes.MultiSurface)
#            exporter.addFeatures(my_layer.getFeatures())
#
#        if source_in is None:
#            raise QgsProcessingException(self.invalidSourceError(parameters, "INPUT"))
#
#        # Transform the in source into a vector layer
#        vector_layer_in = source_in.materialize(QgsFeatureRequest(), feedback)
#
#        # Normalize and extract QGS input features
#        qgs_features_in, geom_type = Simplify.normalize_in_vector_layer(vector_layer_in, feedback)#
#
#        # Validate input geometry type
#        if geom_type not in (QgsWkbTypes.LineString, QgsWkbTypes.Polygon):
#            raise QgsProcessingException("Can only process: (Multi)LineString or (Multi)Polygon vector layers")
#
#        (sink, dest_id) = self.parameterAsSink(parameters, "OUTPUT", context,
#                                               vector_layer_in.fields(),
#                                               geom_type,
#                                               vector_layer_in.sourceCrs())
#
#        # Validate sink
#        if sink is None:
#            raise QgsProcessingException(self.invalidSinkError(parameters, "OUTPUT"))
#
#        # Set progress bar to 1%
#        feedback.setProgress(1)
#
#        # Call ReduceBend algorithm
#        rb_return = Simplify.douglas_peucker(qgs_features_in, tolerance, validate_structure, feedback)
#
#        for qgs_feature_out in rb_return.qgs_features_out:
#            sink.addFeature(qgs_feature_out, QgsFeatureSink.FastInsert)#
#
#        # Push some output statistics
#        feedback.pushInfo(" ")
#        feedback.pushInfo("Number of features in: {0}".format(rb_return.in_nbr_features))
#        feedback.pushInfo("Number of features out: {0}".format(rb_return.out_nbr_features))
#        feedback.pushInfo("Number of iteration needed: {0}".format(rb_return.nbr_pass))
#        feedback.pushInfo("Total vertice deleted: {0}".format(rb_return.nbr_vertice_deleted))
#        if validate_structure:
#            if rb_return.is_structure_valid:
#                status = "Valid"
#            else:
#                status = "Invalid"
#            feedback.pushInfo("Debug - State of the internal data structure: {0}".format(status))
#
#        return {"OUTPUT": dest_id}

#        feedback.cancel()
        return {}


