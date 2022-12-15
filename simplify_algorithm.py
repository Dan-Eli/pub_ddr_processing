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
QGIS Plugin for DDR manipulation
"""

import os
import http
import inspect
import json
import requests
import shutil
import tempfile
import zipfile
from datetime import datetime
from dataclasses import dataclass
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
                       QgsProviderRegistry, QgsProcessingParameterAuthConfig,  QgsApplication,  QgsAuthMethodConfig)


global CSZ_THEMES_EN
CSZ_THEMES_EN = [""]

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
    csz_collection_theme: str = ''
    in_project_filename: str = None
    language: str = None
    service_schema_name: str = None
    gpkg_file_name: str = None        # Name of Geopakage containing the vector layers
    control_file_dir: str = None      # Name of temporary directory
    control_file_name: str = None     # Name of the control file
    zip_file_name: str = None         # Name of the zip file
    keep_files: str = None            # Name of the flag to keep the temporary files and directory
    json_document: str = None         # Name of the JSON document
    dst_qgs_project_name: str = None  # Name of the output QGIS project file
    layers: object = None             # List of the layers to process
    csz_themes_en: [] = None          # List of the themes_en for the CSZ
    csz_themes_fr: [] = None          # List of the themes_en for the CSZ


class UserMessageException(Exception):
    """Exception raised when a message (likely an error message) needs to be sent to the User."""
    pass

class Utils():
    """Contains a list of static methods"""

    @staticmethod
    def process_algorithm(self, process_type, parameters, context, feedback):

        # Create the control file data structure
        ctl_file = ControlFile()

        # Extract the parameters
        self.read_parameters(ctl_file, parameters, context, feedback)

        # Validate the parameters
        Utils.validate_parameters(ctl_file, feedback)

#        # Authentication
#        Utils.authentication(ctl_file, feedback)

        # Copy the QGIS project file (.qgs)
        Utils.copy_qgis_project_file(ctl_file, feedback)

        # Remove unselected layers from the .qgs project file
        Utils.remove_unselected_layers(ctl_file, feedback)

        # Copy the selected layers in the GPKG file
        Utils.copy_layer_gpkg(ctl_file, feedback)

        # Creation of the JSON control file
        Utils.create_json_control_file(ctl_file, feedback)

        # Creation of the ZIP file
        Utils.create_zip_file(ctl_file, feedback)

        # Validate the project file
        if process_type == "VALIDATE":
            DdrValidate.validate_project_file(ctl_file, parameters, context, feedback)
        elif process_type == "PUBLISH":
            DdrPublish.publish_project_file(ctl_file, parameters, context, feedback)
        elif process_type == "UNPUBLISH":
            DdrUnpublish.unpublish_project_file(ctl_file, parameters, context, feedback)
        else:
            raise UserMessageException(f"Internal error. Unknown Process Type: {process_type}")


        # Restoring original .qgs project file
        Utils.restore_original_project_file(ctl_file, feedback)

        # Deleting the temporary directory and files
        # import web_pdb; web_pdb.set_trace()
        Utils.delete_dir_file(ctl_file, feedback)

        return


    @staticmethod
    def get_date_time():
        """Extract the current date and time """

        now = datetime.now()  # current date and time
        date_time = now.strftime("%Y-%m-%d %H:%M:%S")

        return date_time

    @staticmethod
    def create_json_control_file(ctl_file, feedback):
        """Creation and writing of the JSON control file"""

        # Creation of the JSON control file
        json_control_file = {
            "generic_parameters": {
                "department": ctl_file.department,
                "download_info_id": ctl_file.download_info_id,
                "email": ctl_file.email,
                "metadata_uuid": ctl_file.metadata_uuid,
                "qgis_server_id": ctl_file.qgs_server_id,
                "download_package_name": ctl_file.download_package_name,
                "core_subject_term": ctl_file.core_subject_term,
                "czs_collection_theme": ctl_file.csz_collection_theme
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

        str_date_time = Utils.get_date_time()
        feedback.pushInfo(f"{str_date_time} - INFO: Creation of the JSON control file: {ctl_file.control_file_name}")

        return

    @staticmethod
    def extact_csz_themes(ctl_file, json_response):
        """Extract the English and French theme from the JSON response"""

        global CSZ_THEMES_EN
        CSZ_THEMES_EN = []
        CSZ_THEMES_EN.append("40b7310c-1409-4fa8-a007-eda4fbb99fa1")
        ctl_file.csz_themes_en = []
        ctl_file.csz_themes_fr = []
        for item in json_response:
            title = item['title']
            theme_en = title['en']
            theme_fr = title['fr']
            CSZ_THEMES_EN.append(theme_en)
            ctl_file.csz_themes_en.append(theme_en)
            ctl_file.csz_themes_fr.append(theme_fr)

    @staticmethod
    def read_csz_themes(ctl_file, feedback):
        """Read the CSZ themes from end service end point"""

        url = "https://qgis.ddr-stage.services.geo.ca/api/czs_themes"
        str_date_time = Utils.get_date_time()

        global ACCESS_TOKEN

        str_date_time = Utils.get_date_time()
        headers = {'accept': 'application/json',
                   'Authorization': 'Bearer ' + ACCESS_TOKEN}
        print(headers)
#        import web_pdb;  web_pdb.set_trace()
        try:
            feedback.pushInfo(f"{str_date_time} - INFO: HTTP Put Request: {url}")
            response = requests.get(url, verify=False, headers=headers)
            status = response.status_code

            print (status)
            if status == 200:
                feedback.pushInfo(f"{str_date_time} - INFO: Satus code: {str(status)}")
                msg = "Reads the available Clip Zip Ship Themes."
                feedback.pushInfo(f"{str_date_time} - INFO: {msg}")
                json_response = response.json()
                print (json_response)
                Utils.extact_csz_themes(ctl_file, json_response)
        except Exception:
            print ('ca plante....')


    @staticmethod
    def create_access_token(username, password, ctl_file, feedback):
        """Authentication of the username/password in order to get the acces token"""

        url = 'https://qgis.ddr-stage.services.geo.ca/api/login'
        str_date_time = Utils.get_date_time()
        headers = {"accept": "application/json",
                   "Content-type": "application/json"}

        feedback.pushInfo(f"{str_date_time} - INFO: Authentication to DDR")
        feedback.pushInfo(f"{str_date_time} - INFO: HTTP Put Request: {url}")
        feedback.pushInfo(f"{str_date_time} - INFO: HTTP Headers: {str(headers)}")
        json_doc = { "password": password,
                     "username": username}
        print (str(json_doc))

        try:
            feedback.pushInfo(f"{str_date_time} - INFO: HTTP Put Request: {url}")
            response = requests.post(url, verify=False, headers=headers, json=json_doc)
            status = response.status_code
            if status == 200:
                feedback.pushInfo(f"{str_date_time} - INFO: Satus code: {str(status)}")
                msg = "A token or a refresh token is given to the user"
                feedback.pushInfo(f"{str_date_time} - INFO: {msg}")
                json_response = response.json()
                # Store the access token in a global variable for access by other entry points
                global ACCESS_TOKEN
                ACCESS_TOKEN = json_response["access_token"]
                expires_in = json_response["expires_in"]
                refresh_token = json_response["refresh_token"]
                refresh_expires_in = str(json_response["refresh_expires_in"])
                token_type = json_response["token_type"]
                feedback.pushInfo(f"{str_date_time} - INFO: Access token: {ACCESS_TOKEN}")
                feedback.pushInfo(f"{str_date_time} - INFO: Expire in: {str(expires_in)}")
                feedback.pushInfo(f"{str_date_time} - INFO: Refresh token: {refresh_token}")
                feedback.pushInfo(f"{str_date_time} - INFO: Refresh expire in: {str(refresh_expires_in)}")
                feedback.pushInfo(f"{str_date_time} - INFO: Token type: {token_type}")
            elif status in [400, 401]:
                feedback.pushInfo(f"{str_date_time} - ERROR: Satus code: {str(status)}")
                msg = "Bad request received on the server"
                feedback.pushInfo(f"{str_date_time} - INFO: {msg}")
                json_response = response.json()
                print (json_response)
                detail = json_response["detail"]
                detail_fr = json_response["detail_fr"]
                status = json_response["status"]
                title = str(json_response["title"])
                type = json_response["type"]
                feedback.pushInfo(f"{str_date_time} - ERROR: Detail: {detail}")
                feedback.pushInfo(f"{str_date_time} - ERROR: Detail fr: {str(detail_fr)}")
                feedback.pushInfo(f"{str_date_time} - ERROR: Status: {str(status)}")
                feedback.pushInfo(f"{str_date_time} - ERROR: Title: {str(title)}")
                feedback.pushInfo(f"{str_date_time} - ERROR: Type: {type}")
            else:
                feedback.pushInfo(f"{str_date_time} - ERROR: Satus code: {str(status)}")
                status_msg = http.client.responses[int(response.status_code)]
                feedback.pushInfo(f"{str_date_time} - ERROR: Status message: {status_msg}")

        except requests.exceptions.RequestException as e:
            raise UserMessageException(f"Major problem with the DDR Publication API: {url}")
        return

    @staticmethod
    def copy_qgis_project_file(ctl_file, feedback):
        """Creates a copy of the QGIS project file"""

        qgs_project = QgsProject.instance()
        str_date_time = Utils.get_date_time()
        ctl_file.src_qgs_project_name = qgs_project.fileName()  # Extract the name of the QGS project file

        # Validate that a file QGS project file is present
        if ctl_file.src_qgs_project_name is None:
            raise UserMessageException("A QGS project file is not loaded...")

        # Validate the extension of the QGS project file
        extension = PurePath(ctl_file.src_qgs_project_name).suffix
        if extension != ".qgs":
            raise UserMessageException("The QGIS project file extension must be '.qgs' not: '{0}".format(extension))

        # Validate that the project is saved before the processing
        if qgs_project.isDirty():
            raise UserMessageException("The QGIS project file must be saved before starting the DDR publication")

        # Create temporary directory
        ctl_file.control_file_dir = tempfile.mkdtemp(prefix='qgis_')
        feedback.pushInfo(f"{str_date_time} - INFO: Temporary directory created: {ctl_file.control_file_dir}")

        # Copy the QGIS project file (.qgs) in the temporary directory
        ctl_file.in_project_filename = Path(ctl_file.src_qgs_project_name).name
        dst_qgs_project_name = os.path.join(ctl_file.control_file_dir, ctl_file.in_project_filename)

        # Save as... under the new name in the temporary directory
        qgs_project.write(dst_qgs_project_name)
        feedback.pushInfo(f"{str_date_time} - INFO: QGIS project file save as: {dst_qgs_project_name}")

    @staticmethod
    def remove_unselected_layers(ctl_file, feedback):
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
                str_date_time = Utils.get_date_time()
                feedback.pushInfo(f"{str_date_time} - INFO: Removing layer: {layer.name()} from the project file")
                qgs_project.removeMapLayer(layer.id())

        if qgs_project.isDirty():
            # File needs to be saved
            qgs_project_file_name = qgs_project.fileName()
            qgs_project.write(qgs_project_file_name)

        return

    @staticmethod
    def copy_layer_gpkg(ctl_file, feedback):
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
                    str_date_time = Utils.get_date_time()
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

    @staticmethod
    def create_zip_file(ctl_file, feedback):
        """Create the zip file"""

        # Change working directory to the temporary directory
        current_dir = os.getcwd()  # Save current directory
        os.chdir(ctl_file.control_file_dir)

        # Create the zip file
        lst_file_to_zip = [Path(ctl_file.control_file_name).name,
                           Path(ctl_file.gpkg_file_name).name,
                           Path(ctl_file.in_project_filename).name]
        ctl_file.zip_file_name = os.path.join(ctl_file.control_file_dir, "ddr_publish.zip")
        str_date_time = Utils.get_date_time()
        feedback.pushInfo(f"{str_date_time} - INFO: Creating the zip file: {ctl_file.zip_file_name}")
        with zipfile.ZipFile(ctl_file.zip_file_name, mode="w") as archive:
            for file_to_zip in lst_file_to_zip:
                archive.write(file_to_zip)

        # Reset the current directory
        os.chdir(current_dir)

    @staticmethod
    def validate_parameters(ctl_file, feedback):
        """Validate the parameters"""

        # Validate that there is no duplicate layer name
        tmp_layers = []
        for layer in ctl_file.layers:
            tmp_layers.append(layer.name())

        for tmp_layer in tmp_layers:
            if tmp_layers.count(tmp_layer) > 1:
                # Layer is not unique
                raise UserMessageException(f"Remove duplicate layer: {tmp_layer} in QGS project file")

    @staticmethod
    def restore_original_project_file(ctl_file, feedback):
        """Restore the original project file"""

        qgs_project = QgsProject.instance()

        # Reopen the original project file
        str_date_time = Utils.get_date_time()
        feedback.pushInfo(
            f"{str_date_time} - INFO: Restoring original project file (.qgs): {ctl_file.src_qgs_project_name}")
        qgs_project.read(ctl_file.src_qgs_project_name)

    @staticmethod
    def delete_dir_file(ctl_file, feedback):
        """Delete the temporary directory and files"""

        if ctl_file.keep_files == "No":
            # Delete the temporary directory and all its content
            shutil.rmtree(ctl_file.control_file_dir)
            str_date_time = Utils.get_date_time()
            feedback.pushInfo(f"{str_date_time} - INFO: Deleting temporary directory and content: {ctl_file.control_file_dir}")


class UtilsGui():
    """Contains a list of static methods"""

    lst_department = ['eccc',  'nrcan']

    HELP_USAGE = """
        <b>Usage</b>
        <u>Select the input vector layer(s) to publish</u> : Only select the layers you wish to publish. Non vector layers \
        will not appear in the list of selectable layers.
        <u>Select the department</u> : Select which department own the publication.
        <u>Select the download info ID</u> : Download ID info (no choice).
        <u>Enter your email address</u> : Email address used to send publication notification.
        <u>Select the QGIS server</u> : Name of the QGIS server used for the publication (no choice).
        <u>Select the schema named used for publication</u> : Name of the Schema used for the publication in the QGIS server.
        <u>Keep temporary files (for debug purpose)</u> : Flag (Yes/No) for keeping/deleting temporary files.
    """

    def auth_configuration(self):
        print ("coco")

    @staticmethod
    def add_username(self):

        self.addParameter(
            QgsProcessingParameterAuthConfig('AUTHENTICATION', 'Authentication Configuration', defaultValue=None))


    @staticmethod
    def add_password(self):

        self.addParameter(QgsProcessingParameterString(
            name="PASSWORD",
            defaultValue="Dani3Eli!",
            description=self.tr('Enter your DDR password (will not be hidden)')))

    @staticmethod
    def add_layers(self):
        self.addParameter(QgsProcessingParameterMultipleLayers(
                name='LAYERS',
                description=self.tr("Select the input vector layer(s)  to publish "),
                layerType=QgsProcessing.TypeVectorAnyGeometry))


    @staticmethod
    def add_department(self):

        self.addParameter(QgsProcessingParameterEnum(
            name='DEPARTMENT',
            description=self.tr("Select the department"),
            options=UtilsGui.lst_department,
            defaultValue="nrcan",
            usesStaticStrings=True,
            allowMultiple=False))

    def add_uuid(self):

        import uuid
        idd = uuid.uuid4()
        self.addParameter(QgsProcessingParameterString(
            name="METADATA_UUID",
            defaultValue=str(idd),
            description=self.tr('Enter the metadata UUID')))

    def add_download_info(self):

        lst_download_info_id = ["DDR_DOWNLOAD1"]
        self.addParameter(QgsProcessingParameterEnum(
            name='DOWNLOAD_INFO_ID',
            description=self.tr("Select the download info ID"),
            options=lst_download_info_id,
            defaultValue=lst_download_info_id[0],
            usesStaticStrings=True,
            allowMultiple=False))

    def add_email(self):

        self.addParameter(QgsProcessingParameterString(
            name="EMAIL",
            defaultValue="daniel.pilon@nrcan-rncan.gc.ca",
            description=self.tr('Enter your email address')))

    def add_qgs_server_id(self):

        lst_qgs_server_id = ['DDR_QGS1']
        self.addParameter(QgsProcessingParameterEnum(
            name='QGS_SERVER_ID',
            description=self.tr('Select the QGIS server'),
            options=lst_qgs_server_id,
            defaultValue=lst_qgs_server_id[0],
            usesStaticStrings=True,
            allowMultiple=False))

    def add_language(self):

        lst_language = ['English', 'French']
        self.addParameter(QgsProcessingParameterEnum(
            name='LANGUAGE',
            description=self.tr('Select the service language'),
            options=lst_language,
            defaultValue= lst_language[0],
            usesStaticStrings=True,
            allowMultiple=False))

    def add_service_schema_name(self):

        self.addParameter(QgsProcessingParameterEnum(
            name='SERVICE_SCHEMA_NAME',
            description=self.tr("Select the schema name used for publication"),
            options=UtilsGui.lst_department,
            usesStaticStrings=True,
            defaultValue="nrcan",
            allowMultiple=False))

    def add_csz_themes(self):

        self.addParameter(QgsProcessingParameterEnum(
            name='CSZ_THEMES',
            description=self.tr("Select the theme under which you want to publish your project in the clip ship zip (CSZ)"),
            options=CSZ_THEMES_EN,
            usesStaticStrings=True,
            defaultValue="coco",
            allowMultiple=False))

    def add_keek_files(self):

        lst_flag = ['Yes', 'No']
        self.addParameter(QgsProcessingParameterEnum(
            name='KEEP_FILES',
            description=self.tr('Keep temporary files (for debug purpose)'),
            options=lst_flag,
            defaultValue=lst_flag[0],
            usesStaticStrings=True,
            allowMultiple=False))

    def read_parameters(self, ctl_file, parameters, context, feedback):

#        ctl_file.username = self.parameterAsString(parameters, 'USERNAME', context)
#        ctl_file.password = self.parameterAsString(parameters, 'PASSWORD', context)
        ctl_file.department = self.parameterAsString(parameters, 'DEPARTMENT', context)
        ctl_file.download_info_id = self.parameterAsString(parameters, 'DOWNLOAD_INFO_ID', context)
        ctl_file.metadata_uuid = self.parameterAsString(parameters, 'METADATA_UUID', context)
        ctl_file.email = self.parameterAsString(parameters, 'EMAIL', context)
        ctl_file.qgs_server_id = self.parameterAsString(parameters, 'QGS_SERVER_ID', context)
        ctl_file.language = self.parameterAsString(parameters, 'LANGUAGE', context)
        ctl_file.service_schema_name = self.parameterAsString(parameters, 'SERVICE_SCHEMA_NAME', context)
        ctl_file.keep_files = self.parameterAsString(parameters, 'KEEP_FILES', context)
        ctl_file.csz_collection_theme = self.parameterAsString(parameters, 'CSZ_THEMES', context)
        ctl_file.layers = self.parameterAsLayerList(parameters, 'LAYERS', context)


class DdrPublish(QgsProcessingAlgorithm):
    """Main class defining the Simplify algorithm as a QGIS processing algorithm.
    """

    def tr(self, string):  # pylint: disable=no-self-use
        """Returns a translatable string with the self.tr() function.
        """
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):  # pylint: disable=no-self-use
        """Returns a new copy of the algorithm.
        """
        return DdrPublish()

    def name(self):  # pylint: disable=no-self-use
        """Returns the unique algorithm name.
        """
        return 'publish'

    def displayName(self):  # pylint: disable=no-self-use
        """Returns the translated algorithm name.
        """
        return self.tr('Publish Project File')

    def group(self):
        """Returns the name of the group this algorithm belongs to.
        """
        return self.tr(self.groupId())

    def groupId(self):  # pylint: disable=no-self-use
        """Returns the unique ID of the group this algorithm belongs to.
        """
        return 'Management'

    def flags(self):

        return super().flags() | QgsProcessingAlgorithm.FlagNoThreading

    def shortHelpString(self):
        """Returns a localised short help string for the algorithm.
        """
        help_str = """
    This plugin publishes the layers stored in a .qgs project file to the QGS server DDR repository. \
    It can only publish vector layer but the layers can be stored in any format supported by QGIS (e.g. GPKG, \
    SHP, PostGIS, ...).  The style, service information, metadata stored in the .qgs project file will follow. \
    A message is displayed in the log and an email is sent to the user informing the latter on the status of \
    the publication. 
        
        """

        help_str += help_str + UtilsGui.HELP_USAGE

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

        UtilsGui.add_layers(self)
        UtilsGui.add_department(self)
        UtilsGui.add_uuid(self)
        UtilsGui.add_download_info(self)
        UtilsGui.add_email(self)
        UtilsGui.add_qgs_server_id(self)
        UtilsGui.add_language(self)
        UtilsGui.add_service_schema_name(self)
        UtilsGui.add_csz_themes(self)
        UtilsGui.add_keek_files(self)

    def read_parameters(self, ctl_file, parameters, context, feedback):
        """Reads the different parameters in the form and stores the content in the data structure"""

        UtilsGui.read_parameters(self, ctl_file, parameters, context, feedback)

        return

    @staticmethod
    def publish_project_file(ctl_file, parameters, context, feedback):
        """"""

        url = 'https://qgis.ddr-stage.services.geo.ca/api/processes'
        str_date_time = Utils.get_date_time()
        headers = {'accept': 'application/json',
                   'Authorization': 'Bearer ' + ACCESS_TOKEN}
        files = {'zip_file': open(ctl_file.zip_file_name, 'rb')}

        feedback.pushInfo(f"{str_date_time} - INFO: Publishing to DDR")
        feedback.pushInfo(f"{str_date_time} - INFO: HTTP Put Request: {url}")
        feedback.pushInfo(f"{str_date_time} - INFO: HTTP Headers: {str(headers)}")
        feedback.pushInfo(f"{str_date_time} - INFO: Zip file to publish: {ctl_file.zip_file_name}")

        try:
            feedback.pushInfo(f"{str_date_time} - INFO: HTTP Put Request: {url}")
            response = requests.put(url, files=files, verify=False, headers=headers)
            status = response.status_code
            if status == 204:
                feedback.pushInfo(f"{str_date_time} - INFO: Satus code: {str(status)}")
                msg = "Successfully exported the data and published the project file in QGIS Server"
                feedback.pushInfo(f"{str_date_time} - INFO: {msg}")
            else:
                try:
                    json_response = response.json()
                    detail = json_response['detail']
                    detail_fr = json_response['detail_fr']
                    status = json_response['status']
                    title = json_response['title']
                except (AttributeError, KeyError):
                    feedback.pushInfo(f"{str_date_time} - ERROR: Major problem with the DDR publication API")
                    feedback.pushInfo(f"{str_date_time} - ERROR: Status code: {status}")
                    status_msg = http.client.responses[int(response.status_code)]
                    feedback.pushInfo(f"{str_date_time} - ERROR: Status message: {status_msg}")
                    raise UserMessageException(f"The response of the DDR Publication API is corrupted: {url}")

                feedback.pushInfo(f"{str_date_time} - ERROR: {status}")
                feedback.pushInfo(f"{str_date_time} - ERROR: {title}")
                for item in [detail, detail_fr]:
                    lines = detail.split("\n")
                    for line in lines:
                        feedback.pushInfo(f"{str_date_time} - ERROR: {line}")

        except requests.exceptions.RequestException as e:
            raise UserMessageException(f"Major problem with the DDR Publication API: {url}")
        return

    def processAlgorithm(self, parameters, context, feedback):
        """Main method that extract parameters and call Simplify algorithm.
        """

        try:
            Utils.process_algorithm(self, "PUBLISH", parameters, context, feedback)
        except UserMessageException as e:
            str_date_time = Utils.get_date_time()
            feedback.pushInfo(f"{str_date_time} - ERROR: Publish process")
            feedback.pushInfo(f"{str_date_time} - ERROR: {str(e)}")

        return {}


class DdrValidate(QgsProcessingAlgorithm):
    """Main class defining the Simplify algorithm as a QGIS processing algorithm.
    """

    def tr(self, string):  # pylint: disable=no-self-use
        """Returns a translatable string with the self.tr() function.
        """
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):  # pylint: disable=no-self-use
        """Returns a new copy of the algorithm.
        """
        return DdrValidate()

    def name(self):  # pylint: disable=no-self-use
        """Returns the unique algorithm name.
        """
        return 'validate'

    def displayName(self):  # pylint: disable=no-self-use
        """Returns the translated algorithm name.
        """
        return self.tr('Validate Project File')

    def group(self):
        """Returns the name of the group this algorithm belongs to.
        """
        return self.tr(self.groupId())

    def groupId(self):  # pylint: disable=no-self-use
        """Returns the unique ID of the group this algorithm belongs to.
        """
        return 'Management'

    def flags(self):

        return super().flags() | QgsProcessingAlgorithm.FlagNoThreading

    def shortHelpString(self):
        """Returns a localised short help string for the algorithm.
        """
        help_str = """
    This processing plugin validates the content of a QGIS project file (.qgs) and its control file. \
    If the validation pass, the project can be publish the project in the QGIS server. If the validation fail, \
    you can edit the QGIS project file and/or the control file and rerun the Validate Publication \
    plugin. This plugin does not write anything into the QGIS server so you can rerun it safely until \
    there is no error and than run the "Publish Vector Layer" Processing Plugin. """

        help_str += help_str + UtilsGui.HELP_USAGE

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

#        UtilsGui.add_username(self)
#        UtilsGui.add_password(self)
        UtilsGui.add_layers(self)
        UtilsGui.add_department(self)
        UtilsGui.add_uuid(self)
        UtilsGui.add_download_info(self)
        UtilsGui.add_email(self)
        UtilsGui.add_qgs_server_id(self)
        UtilsGui.add_language(self)
        UtilsGui.add_service_schema_name(self)
        UtilsGui.add_csz_themes(self)
        UtilsGui.add_keek_files(self)

    def read_parameters(self, ctl_file, parameters, context, feedback):
        """Reads the different parameters in the form and stores the content in the data structure"""

        UtilsGui.read_parameters(self, ctl_file, parameters, context, feedback)

        return

    @staticmethod
    def validate_project_file(ctl_file, parameters, context, feedback):
        """"""

        global ACCESS_TOKEN

        str_date_time = Utils.get_date_time()
        url = 'https://qgis.ddr-stage.services.geo.ca/api/validate'
        headers = {'accept': 'application/json',
                   'Authorization': 'Bearer ' + ACCESS_TOKEN}
        print (headers)
        files = {'zip_file': open(ctl_file.zip_file_name, 'rb')}
        feedback.pushInfo(f"{str_date_time} - INFO: Publishing to DDR")
        feedback.pushInfo(f"{str_date_time} - INFO: HTTP Put Request: {url}")
        feedback.pushInfo(f"{str_date_time} - INFO: HTTP Headers: {str(headers)}")
        feedback.pushInfo(f"{str_date_time} - INFO: Zip file to publish: {ctl_file.zip_file_name}")
        try:
            feedback.pushInfo(f"{str_date_time} - INFO: HTTP Post Request: {url}")
            response = requests.post(url, files=files, verify=False, headers=headers)
            status = response.status_code
            if status == 200:
                status_msg = "INFO"
            else:
                status_msg = "ERROR"

            try:
                json_response = response.json()
                results = json.dumps(json_response, indent=4)
            except (AttributeError, KeyError):
                feedback.pushInfo(f"{str_date_time} - ERROR: Major problem with the DDR publication API")
                feedback.pushInfo(f"{str_date_time} - ERROR: Status code: {status}")
                status_msg = http.client.responses[int(response.status_code)]
                feedback.pushInfo(f"{str_date_time} - ERROR: Status message: {status_msg}")
                raise UserMessageException(f"The response of the DDR Publication API is corrupted: {url}")

            feedback.pushInfo(f"{str_date_time} - {status_msg}: {status}")
            lines = results.split("\n")
            for line in lines:
                leading_sp = len(line) - len(line.lstrip())  # Extract the number of leading spaces
                line = line.replace(line[0:leading_sp],"."*leading_sp)  # Replace leading spaces by "." (dots)
                feedback.pushInfo(f"{str_date_time} - {status_msg}: {line}")

        except requests.exceptions.RequestException as e:
            raise UserMessageException(f"Major problem with the DDR Publication API: {url}")
        return

    def processAlgorithm(self, parameters, context, feedback):
        """Main method that extract parameters and call Simplify algorithm.
        """

        try:
            Utils.process_algorithm(self, "VALIDATE", parameters, context, feedback)
        except UserMessageException as e:
            str_date_time = Utils.get_date_time()
            feedback.pushInfo(f"{str_date_time} - ERROR: Validate process")
            feedback.pushInfo(f"{str_date_time} - ERROR: {str(e)}")

        return {}


class DdrUnpublish(QgsProcessingAlgorithm):
    """Main class defining the Unpublish algorithm as a QGIS processing algorithm.
    """

    def tr(self, string):  # pylint: disable=no-self-use
        """Returns a translatable string with the self.tr() function.
        """
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):  # pylint: disable=no-self-use
        """Returns a new copy of the algorithm.
        """
        return DdrUnpublish()

    def name(self):  # pylint: disable=no-self-use
        """Returns the unique algorithm name.
        """
        return 'unpublish'

    def displayName(self):  # pylint: disable=no-self-use
        """Returns the translated algorithm name.
        """
        return self.tr('Unpublish Project File')

    def group(self):
        """Returns the name of the group this algorithm belongs to.
        """
        return self.tr(self.groupId())

    def groupId(self):  # pylint: disable=no-self-use
        """Returns the unique ID of the group this algorithm belongs to.
        """
        return 'Management'

    def flags(self):

        return super().flags() | QgsProcessingAlgorithm.FlagNoThreading

    def shortHelpString(self):
        """Returns a localised short help string for the algorithm.
        """
        help_str = """This processing plugin unpublishes the content of a QGIS project file (.qgs) stored in the QGIS Server.
        
        """

        help_str += help_str + UtilsGui.HELP_USAGE

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

        UtilsGui.add_layers(self)
        UtilsGui.add_department(self)
        UtilsGui.add_uuid(self)
        UtilsGui.add_download_info(self)
        UtilsGui.add_email(self)
        UtilsGui.add_qgs_server_id(self)
        UtilsGui.add_language(self)
        UtilsGui.add_service_schema_name(self)
        UtilsGui.add_keek_files(self)

    def read_parameters(self, ctl_file, parameters, context, feedback):
        """Reads the different parameters in the form and stores the content in the data structure"""

        UtilsGui.read_parameters(self, ctl_file, parameters, context, feedback)

        return

    @staticmethod
    def unpublish_project_file(ctl_file, parameters, context, feedback):
        """Unpublish a QGIS project file """

        str_date_time = Utils.get_date_time()
        url = 'https://qgis.ddr-stage.services.geo.ca/api/processes'
        headers = {'accept': 'application/json',
                   'Authorization': 'Bearer ' + ACCESS_TOKEN}
        files = {'zip_file': open(ctl_file.zip_file_name, 'rb')}
        feedback.pushInfo(f"{str_date_time} - INFO: Publishing to DDR")
        feedback.pushInfo(f"{str_date_time} - INFO: HTTP Put Request: {url}")
        feedback.pushInfo(f"{str_date_time} - INFO: HTTP Headers: {str(headers)}")
        feedback.pushInfo(f"{str_date_time} - INFO: Zip file to publish: {ctl_file.zip_file_name}")
        try:
            feedback.pushInfo(f"{str_date_time} - INFO: HTTP Request: {url}")
            response = requests.delete(url, files=files, verify=False, headers=headers)
            status = response.status_code
            if status == 204:
                feedback.pushInfo(f"{str_date_time} - INFO: Satus code: 204")
                msg = "Successfully deleted the Service in QGIS Server"
                feedback.pushInfo(f"{str_date_time} - INFO: {msg}")
            else:
                try:
                    json_response = response.json()
                    detail = json_response['detail']
                    detail_fr = json_response['detail_fr']
                    status = json_response['status']
                    title = json_response['title']
                except (AttributeError, KeyError):
                    feedback.pushInfo(f"{str_date_time} - ERROR: Major problem with the DDR publication API")
                    feedback.pushInfo(f"{str_date_time} - ERROR: Status code: {status}")
                    status_msg = http.client.responses[int(response.status_code)]
                    feedback.pushInfo(f"{str_date_time} - ERROR: Status message: {status_msg}")
                    raise UserMessageException(f"The response of the DDR Publication API is corrupted: {url}")

                feedback.pushInfo(f"{str_date_time} - ERROR: {status}")
                feedback.pushInfo(f"{str_date_time} - ERROR: {title}")
                for item in [detail, detail_fr]:
                    lines = detail.split("\n")
                    for line in lines:
                        feedback.pushInfo(f"{str_date_time} - ERROR: {line}")

        except requests.exceptions.RequestException as e:
            raise UserMessageException(f"Major problem with the DDR Publication API: {url}")
        return

    def processAlgorithm(self, parameters, context, feedback):
        """Main method that extract parameters and call Simplify algorithm.
        """
        try:
            Utils.process_algorithm(self, "UNPUBLISH", parameters, context, feedback)
        except UserMessageException as e:
            str_date_time = Utils.get_date_time()
            feedback.pushInfo(f"{str_date_time} - ERROR: Unpublish process")
            feedback.pushInfo(f"{str_date_time} - ERROR: {str(e)}")

        return {}


class DdrLogin(QgsProcessingAlgorithm):
    """Main class defining the DDR Login algorithm as a QGIS processing algorithm.
    """

    def tr(self, string):  # pylint: disable=no-self-use
        """Returns a translatable string with the self.tr() function.
        """
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):  # pylint: disable=no-self-use
        """Returns a new copy of the algorithm.
        """
        return DdrLogin()

    def name(self):  # pylint: disable=no-self-use
        """Returns the unique algorithm name.
        """
        return 'login'

    def displayName(self):  # pylint: disable=no-self-use
        """Returns the translated algorithm name.
        """
        return self.tr('DDR Login')

    def group(self):
        """Returns the name of the group this algorithm belongs to.
        """
        return self.tr(self.groupId())

    def groupId(self):  # pylint: disable=no-self-use
        """Returns the unique ID of the group this algorithm belongs to.
        """
        return 'Authentication (first step)'

    def flags(self):

        return super().flags() | QgsProcessingAlgorithm.FlagNoThreading

    def shortHelpString(self):
        """Returns a localised short help string for the algorithm.
        """
        help_str = """This processing plugin unpublishes the content of a QGIS project file (.qgs) stored in the QGIS Server.
                   <img src=C:\\Users\\dpilon\\AppData\\Roaming\\QGIS\\QGIS3\\profiles\\default\\python\\plugins\\pub_ddr_processing\logo.png>
                   """

        help_str += help_str + UtilsGui.HELP_USAGE

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

        print ("Here change the name of the method...")
        UtilsGui.add_username(self)

    def auth_method_id(self):
        print ("coco12345")

    def read_parameters(self, ctl_file, parameters, context, feedback):
        """Reads the different parameters in the form and stores the content in the data structure"""

        auth_method = self.parameterAsString(parameters, 'AUTHENTICATION', context)

        # Get the application's authentication manager
        auth_mgr = QgsApplication.authManager()

        # Create an empty authmethodconfig object
        auth_cfg = QgsAuthMethodConfig()

        # Load config from manager to the new config instance and decrypt sensitive data
        auth_mgr.loadAuthenticationConfig(auth_method, auth_cfg, True)

        # Get the configuration information (including username and password)
        auth_cfg.configMap()
        auth_info = auth_cfg.configMap()

        try:
            username = auth_info['username']
            password = auth_info['password']
        except KeyError:
            raise UserMessageException("Unable to extract username/password from QGIS authetication system")

        return (username, password)

    def processAlgorithm(self, parameters, context, feedback):
        """Main method that extract parameters and call Simplify algorithm.
        """

        try:
            # Create the control file data structure
            ctl_file = ControlFile()
            (username, password) = self.read_parameters(ctl_file, parameters, context, feedback)

            Utils.create_access_token(username, password, ctl_file, feedback)

            Utils.read_csz_themes(ctl_file, feedback)

        except UserMessageException as e:
            str_date_time = Utils.get_date_time()
            feedback.pushInfo(f"{str_date_time} - ERROR: Login process")
            feedback.pushInfo(f"{str_date_time} - ERROR: {str(e)}")

        return {}
