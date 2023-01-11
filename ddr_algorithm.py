# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module
# pylint: disable=too-many-lines
# pylint: disable=useless-return
# pylint: disable=too-few-public-methods
# pylint: disable=relative-beyond-top-level

# /***************************************************************************
# ddr_algorithm.py
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
import http.client
import inspect
import json
import requests
import shutil
import tempfile
import time
import unicodedata
import zipfile
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.core import (Qgis, QgsProcessing, QgsProcessingAlgorithm, QgsProcessingParameterDistance,
                       QgsProcessingParameterFeatureSource, QgsProcessingParameterFeatureSink,
                       QgsFeatureSink, QgsFeatureRequest, QgsLineString, QgsWkbTypes, QgsGeometry,
                       QgsProcessingException, QgsProcessingParameterMultipleLayers, QgsMapLayer,
                       QgsVectorLayerExporter, QgsVectorFileWriter, QgsProject, QgsProcessingParameterEnum,
                       QgsProcessingParameterString, QgsProcessingParameterFolderDestination,
                       QgsMapLayerStyleManager, QgsReadWriteContext, QgsDataSourceUri,  QgsDataProvider,
                       QgsProviderRegistry, QgsProcessingParameterAuthConfig,  QgsApplication,  QgsAuthMethodConfig,
                       QgsProcessingParameterFile, QgsProcessingParameterDefinition)


class ResponseCodes(object):
    """This class manages response codes from the DDR API """

    @staticmethod
    def _push_response(feedback, response, status_code, message):
        """This method displays messages in the log section of the processing tool"""

        try:
            Utils.push_info(feedback, "ERROR: ", f"{status_code} - {message}")
            try:
                json_response = response.json()
                results = json.dumps(json_response, indent=4, ensure_ascii=False)
                Utils.push_info(feedback, "ERROR: ", results, pad_with_dot=True)
            except Exception:
                pass
        except Exception:
            raise UserMessageException(f'JSON response for status code {status_code} is missing or badly formed: {json_response}')

    @staticmethod
    def validate_project_file(feedback, response):
        """This method manages the response codes for the DDR Publisher API Post /validate
        This API validates if a project is compliant when a project is complain it can be published/unpublished"""

        status = response.status_code
        if status == 200:
            json_response = response.json()
            results = json.dumps(json_response, indent=4, ensure_ascii=False)
            Utils.push_info(feedback, "INFO: ", results, pad_with_dot=True)
        elif status == 401:
            ResponseCodes._push_response(feedback, response, 401, "Access token is missing or invalid.")
        elif status == 403:
            ResponseCodes._push_response(feedback, response, 403, "Access token does not have the required scope.")
        elif status == 500:
            ResponseCodes._push_response(feedback, response, 500, "Internal error.")
        else:
            description = http.client.responses[status]
            ResponseCodes._push_response(feedback, response, status, description)

    @staticmethod
    def create_access_token(feedback, response):
        """This method manages the response codes for the DDR Publisher API Post /login
        To log into the DDR API and get a valid token"""

        status = response.status_code

        if status == 200:
            Utils.push_info(feedback, "INFO: A token or a refresh token is given to the user")
            json_response = response.json()
            # Store the access token in a global variable for access by other entry points
            LOGIN_TOKEN.set_token(json_response["access_token"])
            expires_in = json_response["expires_in"]
            refresh_token = json_response["refresh_token"]
            refresh_expires_in = json_response["refresh_expires_in"]
            token_type = json_response["token_type"]
            Utils.push_info(feedback, "INFO: ", f"Access token: {LOGIN_TOKEN.get_token(feedback)[0:29]}...")
            Utils.push_info(feedback, "INFO: ", f"Expire in: {expires_in}")
            Utils.push_info(feedback, "INFO: ", f"Refresh token: {refresh_token[0:29]}...")
            Utils.push_info(feedback, "INFO: ", f"Refresh expire in: {refresh_expires_in}")
            Utils.push_info(feedback, "INFO: ", f"Token type: {token_type}")
        elif status == 400:
            ResponseCodes._push_response(feedback, response, 400, "Bad request received on server.")
        elif status == 401:
            ResponseCodes._push_response(feedback, response, 401, "Invalid credentials provided.")
        else:
            description = http.client.responses[status]
            ResponseCodes._push_response(feedback, response, status, description)

    @staticmethod
    def read_csz_theme(feedback, response):
        """This method manages the response codes for the DDR Publisher API Get /csz_themes
        This method extract the themes from the DDR"""

        status = response.status_code

        if status == 200:
            Utils.push_info(feedback, f"INFO: Status code: {status}")
            msg = "Reading the available Clip Zip Ship Themes."
            Utils.push_info(feedback, f"INFO: {msg}")
            json_response = response.json()
            DDR_INFO.add_themes(json_response)
        elif status == 401:
            ResponseCodes._push_response(feedback, response, 401, "Access token is missing or invalid.")
        elif status == 403:
            ResponseCodes._push_response(feedback, response, 403, "Access does not have the required scope.")
        else:
            description = http.client.responses[status]
            ResponseCodes._push_response(feedback, response, status, description)

    @staticmethod
    def read_ddr_departments(feedback, response):
        """This method manages the response codes for the DDR Publisher API Get /csz_departments
           This method extract the departments from the DDR"""

        status = response.status_code

        if status == 200:
            Utils.push_info(feedback, f"INFO: Status code: {status}")
            msg = "Reading the available DDR departments."
            Utils.push_info(feedback, f"INFO: {msg}")
            json_response = response.json()
            DDR_INFO.add_departments(json_response)
        elif status == 401:
            ResponseCodes._push_response(feedback, response, 401, "Access token is missing or invalid.")
        elif status == 403:
            ResponseCodes._push_response(feedback, response, 403, "Access does not have the required scope.")
        else:
            description = http.client.responses[status]
            ResponseCodes._push_response(feedback, response, status, description)

    @staticmethod
    def read_user_email(feedback, response):
        """This method manages the response codes for the DDR Publisher API Get /ddr_my_email
           This method extract the email associated with user login"""

        status = response.status_code

        if status == 200:
            Utils.push_info(feedback, f"INFO: Status code: {status}")
            msg = "Reading the user email."
            Utils.push_info(feedback, f"INFO: {msg}")
            json_response = response.json()
            DDR_INFO.add_email(json_response)
        elif status == 401:
            ResponseCodes._push_response(feedback, response, 401, "Access token is missing or invalid.")
        elif status == 403:
            ResponseCodes._push_response(feedback, response, 403, "Access does not have the required scope.")
        else:
            description = http.client.responses[status]
            ResponseCodes._push_response(feedback, response, status, description)

    @staticmethod
    def publish_project_file(feedback, response):
        """This method manages the response codes for the DDR Publisher API PUT /services
        """

        status = response.status_code

        if status == 204:
            msg = "Successfully published the project file(s) in QGIS Server."
            Utils.push_info(feedback, f"INFO: {msg}")
        elif status == 401:
            ResponseCodes._push_response(feedback, response, 401, "Access token is missing or invalid.")
        elif status == 403:
            ResponseCodes._push_response(feedback, response, 403, "Access does not have the required scope.")
        elif status == 500:
            ResponseCodes._push_response(feedback, response, 500, "Internal error.")
        else:
            ResponseCodes._push_response(feedback, response, status, "Unknown error")

    @staticmethod
    def unpublish_project_file(feedback, response):
        """This method manages the response codes for the DDR Unpublisher API DELETE /services
           """

        status = response.status_code

        if status == 204:
            msg = "Successfully deleted the Service (data remains in the database)."
            Utils.push_info(feedback, f"INFO: {msg}")
        elif status == 401:
            ResponseCodes._push_response(feedback, response, 401, "Access token is missing or invalid.")
        elif status == 403:
            ResponseCodes._push_response(feedback, response, 403, "Access does not have the required scope.")
        elif status == 500:
            ResponseCodes._push_response(feedback, response, 500, "Internal error.")
        else:
            ResponseCodes._push_response(feedback, response, status, "Unknown error")


class LoginToken(object):
    """This class manages the login token needed to call the different DDR API end points"""

    def __init__(self):

        self.token = None

    def set_token(self, token):
        """This method sets the token """

        self.token = token

    def get_token(self, feedback):
        """This method allows to get the token. If the token is None than an error is rose because the login  was
           not done"""

        if self.token is None:
            # The token has hot been initialised (no login)
            Utils.push_info(feedback, f"ERROR: Login first...")
            raise UserMessageException("The user must login first before doing any access to the DDR")

        return self.token


class DdrInfo(object):
    """This class holds and manages different information extracted from the DDR using the API"""

    def __init__(self):

        self.qgis_layer_name_en = None
        self.qgis_layer_name_fr = None
        self.short_name_en = None
        self.short_name_fr = None
        self.json_theme = []
        self.json_department = []
        self.json_email = []

    def init_project_file(self):

        self.qgis_layer_name_en = []
        self.qgis_layer_name_fr = []
        self.short_name_en = []
        self.short_name_fr = []

    def add_layer(self, src_layer, language):

        short_name = src_layer.shortName()

        # validate that the short name is present
        if short_name is None or short_name == "":
            raise UserMessageException(f"The short name for layer {src_layer.name()} is missing")

        # Validate that the short name is not duplicate
        if language == "EN":
            qgis_layer_name = self.qgis_layer_name_en
        else:
            qgis_layer_name = self.qgis_layer_name_fr

        if short_name not in qgis_layer_name:
            qgis_layer_name.append(short_name)
        else:
            raise UserMessageException(f"Duplicate short name {short_name} for layer {src_layer.name()}")

    def get_layer_short_name(self, src_layer):
        """Get the short name from the layer"""

        return src_layer.shortName()

    def get_nbr_layers(self):

        a = len(self.qgis_layer_name_en)
        b = len(self.qgis_layer_name_fr)
        return max(a, b)


    def add_email(self, json_email):
        """Add the email associated to the login"""

        self.json_email = json_email

    def get_email(self):
        """Get the login associated to the login"""

        return self.json_email

    def add_departments(self, json_department):
        """Add the the departments from the JSON response structure
           Verify the validity of the JSON structure"""

        self.json_department = json_department
        # Verify the structure/content of the JSON document
        try:
            for item in self.json_department:
                acronym = item['qgis_data_store_root_subpath']
        except KeyError:
            # Bad structure raise an exception and crash
            raise UserMessageException("Invalid structure of the JSON theme response from the DDR request")

    def get_department_lst(self):
        """Extract the departments in the form of a list"""

        department_lst = []
        for item in self.json_department:
            department = item['qgis_data_store_root_subpath']
            department_lst.append(department)

        return department_lst

    def add_themes(self, json_theme):
        """Add the the themes from the JSON response structure
           Verify the validity of the JSON structure"""

        self.json_theme = json_theme
        # Verify the structure/content of the JSON document
        try:
            for item in self.json_theme:
                theme_uuid = item['theme_uuid']
                title = item['title']
                # Replace the coma "," by a semi column ";" as QGIS processing enum does not like coma
                title['en'] = title['en'].replace(',', ';')
                title['fr'] = title['fr'].replace(',', ';')
        except KeyError:
            # Bad structure raise an exception and crash
            raise UserMessageException("Invalid structure of the JSON theme response from the DDR request")

    def get_theme_lst(self, language):
        """Extract the themes in the form of a list"""

        if language not in ["fr", "en"]:
            raise UserMessageException("Internal error: Invalid language")
        theme_lst = []
        for item in self.json_theme:
            title = item['title']
            theme_lst.append(title[language])

        return theme_lst

    def get_theme_uuid(self, title):
        """Get the theme UUID for a theme title
           Raise an exception if the theme cannot be find in the list (should not happen...)"""

        if title is None or title == "":

            item_uuid = ""
        else:
            for item in self.json_theme:
                item_uuid = item['theme_uuid']
                item_title = item['title']
                item_title_en = item_title['en']
                item_title_fr = item_title['fr']
                if title in (item_title_en, item_title_fr):
                    break
                else:
                    item_uuid = None

            if item_uuid is None:
                # Nothing was found internal error
                raise UserMessageException(f"Internal error: The 'title' is not found...")

        return item_uuid


DDR_INFO = DdrInfo()

LOGIN_TOKEN = LoginToken()

@dataclass
class ControlFile:
    """Declare the fields in the control control file"""

    download_info_id: str = None
    email: str = None
    metadata_uuid: str = None
    qgis_server_id: str = None
    download_package_name: str = ''
    core_subject_term: str = ''
    in_project_filename: str = None
    language: str = None
    gpkg_file_name: str = None           # Name of Geopackage containing the vector layers
    control_file_dir: str = None         # Name of temporary directory
    control_file_name: str = None        # Name of the control file
    zip_file_name: str = None            # Name of the zip file
    keep_files: str = None               # Name of the flag to keep the temporary files and directory
    json_document: str = None            # Name of the JSON document
    dst_qgs_project_name: str = None     # Name of the output QGIS project file
    qgis_project_file_en: str = None     # Name of the input English QGIS project file
    qgis_project_file_fr: str = None     # Name of the input French QGIS project file
    out_qgs_project_file_en: str = None  # Name out the output English project file
    out_qgs_project_file_fr: str = None  # Name out the output English project file


class UserMessageException(Exception):
    """Exception raised when a message (likely an error message) needs to be sent to the User."""
    pass

class Utils:
    """Contains a list of static methods"""

    @staticmethod
    def process_algorithm(self, process_type, parameters, context, feedback):

        # Init the project files by resetting the layers structures
        DDR_INFO.init_project_file()

        # Create the control file data structure
        ctl_file = ControlFile()

        # Extract the parameters
        self.read_parameters(ctl_file, parameters, context, feedback)

        # Copy the QGIS project file (.qgs)
        Utils.copy_qgis_project_file(ctl_file, feedback)

        # Copy the selected layers in the GPKG file
        Utils.copy_layer_gpkg(ctl_file, feedback)

        # Set the layer data source
        Utils.set_layer_data_source(ctl_file, feedback)

        # Creation of the JSON control file
        Utils.create_json_control_file(ctl_file, feedback)

        # Creation of the ZIP file
        Utils.create_zip_file(ctl_file, feedback)

        # Validate the project file
        if process_type == "VALIDATE":
            DdrValidate.validate_project_file(ctl_file, parameters, context, feedback)
        elif process_type == "PUBLISH":
            # Publish the project file
            DdrPublish.publish_project_file(ctl_file, parameters, context, feedback)
        elif process_type == "UNPUBLISH":
            # Unpublish the project file
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
        theme_uuid = DDR_INFO.get_theme_uuid(ctl_file.csz_collection_theme)

        json_control_file = {
            "generic_parameters": {
                "department": ctl_file.department,
                "download_info_id": ctl_file.download_info_id,
                "email": ctl_file.email,
                "metadata_uuid": ctl_file.metadata_uuid,
                "qgis_server_id": ctl_file.qgs_server_id,
                "download_package_name": ctl_file.download_package_name,
                "core_subject_term": ctl_file.core_subject_term,
                "czs_collection_theme": theme_uuid
            },
            "service_parameters": [
                {
                    "in_project_filename": Path(ctl_file.out_qgs_project_file_en).name,
                    "language": 'English',
                    "service_schema_name": ctl_file.department
                },
                {
                    "in_project_filename": Path(ctl_file.out_qgs_project_file_fr).name,
                    "language": 'French',
                    "service_schema_name": ctl_file.department
                }
            ]
        }

        # Serialize the JSON
        json_object = json.dumps(json_control_file, indent=4, ensure_ascii=False)

        # Write the JSON document
        ctl_file.control_file_name = os.path.join(ctl_file.control_file_dir, "ControlFile.json")
        with open(ctl_file.control_file_name, "w") as outfile:
            outfile.write(json_object)

        Utils.push_info(feedback, f"INFO: Creation of the JSON control file: {ctl_file.control_file_name}")

        return

    @staticmethod
    def read_csz_themes(ctl_file, feedback):
        """Read the CSZ themes from end service end point"""

        url = "https://qgis.ddr-stage.services.geo.ca/api/czs_themes"
        headers = {'accept': 'application/json',
                   'Authorization': 'Bearer ' + LOGIN_TOKEN.get_token(feedback)}
        try:
            Utils.push_info(feedback, f"INFO: HTTP Put Request: {url}")
            response = requests.get(url, verify=False, headers=headers)
            ResponseCodes.read_csz_theme(feedback, response)

        except requests.exceptions.RequestException as e:
            raise UserMessageException(f"Major problem with the DDR Publication API: {url}")

    @staticmethod
    def read_ddr_departments(ctl_file, feedback):
        """Read the DDR departments from end service end point"""

        url = "https://qgis.ddr-stage.services.geo.ca/api/ddr_departments"
        headers = {'accept': 'application/json',
                   'Authorization': 'Bearer ' + LOGIN_TOKEN.get_token(feedback)}
        try:
            Utils.push_info(feedback, f"INFO: HTTP Put Request: {url}")
            response = requests.get(url, verify=False, headers=headers)
            ResponseCodes.read_ddr_departments(feedback, response)

        except requests.exceptions.RequestException as e:
            raise UserMessageException(f"Major problem with the DDR Publication API: {url}")

    @staticmethod
    def read_user_email(ctl_file, feedback):
        """Read the user email from the end service end point"""

        url = "https://qgis.ddr-stage.services.geo.ca/api/ddr_my_email"
        headers = {'accept': 'application/json',
                   'Authorization': 'Bearer ' + LOGIN_TOKEN.get_token(feedback)}
        try:
            Utils.push_info(feedback, f"INFO: HTTP Put Request: {url}")
            response = requests.get(url, verify=False, headers=headers)
            ResponseCodes.read_user_email(feedback, response)

        except requests.exceptions.RequestException as e:
            raise UserMessageException(f"Major problem with the DDR Publication API: {url}")

    @staticmethod
    def create_access_token(username, password, ctl_file, feedback):
        """Authentication of the username/password in order to get the access token"""

        url = 'https://qgis.ddr-stage.services.geo.ca/api/login'
        headers = {"accept": "application/json",
                   "Content-type": "application/json",
                   "charset":"utf-8" }

        Utils.push_info(feedback, "INFO: Authentication to DDR")
        Utils.push_info(feedback, f"INFO: HTTP Put Request: {url}")
        Utils.push_info(feedback, f"INFO: HTTP Headers: {headers}")
        json_doc = { "password": password,
                     "username": username}

        try:
            Utils.push_info(feedback, f"INFO: HTTP Put Request: {url}")
            response = requests.post(url, verify=False, headers=headers, json=json_doc)

            ResponseCodes.create_access_token(feedback, response)

        except requests.exceptions.RequestException as e:
            raise UserMessageException(f"Major problem with the DDR Publication API: {url}")
        return

    @staticmethod
    def copy_qgis_project_file(ctl_file, feedback):
        """Creates a copy of the QGIS project file"""

        qgs_project = QgsProject.instance()

        # Validate that the present QGIS project is saved before the processing
        if qgs_project.isDirty():
            raise UserMessageException("The QGIS project file must be saved before starting the DDR publication")

        # Save the name of the actual QGS project file
        ctl_file.src_qgs_project_name = qgs_project.fileName()

        # Create temporary directory
        ctl_file.control_file_dir = tempfile.mkdtemp(prefix='qgis_')
        Utils.push_info(feedback, "INFO: Temporary directory created: ", ctl_file.control_file_dir)

        # Clear or Close  the actual QGS project
        qgs_project.clear()

        # Read the French QGIS project
        qgs_project.read(ctl_file.qgis_project_file_fr)
        qgis_file_fr = Path(ctl_file.qgis_project_file_fr).name
        ctl_file.out_qgs_project_file_fr = os.path.join(ctl_file.control_file_dir, qgis_file_fr)
        qgs_project.write(ctl_file.out_qgs_project_file_fr)
        Utils.push_info(feedback, "INFO: QGIS project file save as: ", ctl_file.out_qgs_project_file_fr)

        qgs_project = QgsProject.instance()
        for src_layer in qgs_project.mapLayers().values():
            DDR_INFO.add_layer(src_layer, "FR")

        # Read the English QGIS project
        qgs_project.read(ctl_file.qgis_project_file_en)
        qgis_file_en = Path(ctl_file.qgis_project_file_en).name
        ctl_file.out_qgs_project_file_en = os.path.join(ctl_file.control_file_dir, qgis_file_en)
        qgs_project.write(ctl_file.out_qgs_project_file_en)
        Utils.push_info(feedback, "INFO: QGIS project file save as: ",ctl_file.out_qgs_project_file_en)

        qgs_project = QgsProject.instance()
        for src_layer in qgs_project.mapLayers().values():
            DDR_INFO.add_layer(src_layer, "EN")

    @staticmethod
    def copy_layer_gpkg(ctl_file, feedback):
        """Copy the selected layers in the GeoPackage file"""

        ctl_file.gpkg_file_name = os.path.join(ctl_file.control_file_dir, "qgis_vector_layers.gpkg")
        qgs_project = QgsProject.instance()

        total = DDR_INFO.get_nbr_layers()  # Total number of layers to process
        # Loop over each selected layers
        for i, src_layer in enumerate(qgs_project.mapLayers().values()):
            transform_context = QgsProject.instance().transformContext()
            if src_layer.isSpatial():
                if src_layer.type() == QgsMapLayer.VectorLayer:
                    # Only copy vector layer
                    options = QgsVectorFileWriter.SaveVectorOptions()
                    options.layerName = DDR_INFO.get_layer_short_name(src_layer)
                    options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer if Path(
                        ctl_file.gpkg_file_name).exists() else QgsVectorFileWriter.CreateOrOverwriteFile
                    options.feedback = None
                    Utils.push_info(feedback, f"INFO: Copying layer: {src_layer.name()} ({str(i+1)}/{str(total)})")

                    error, err1, err2, err3 = QgsVectorFileWriter.writeAsVectorFormatV3(layer=src_layer,
                                              fileName=ctl_file.gpkg_file_name,
                                              transformContext=transform_context,
                                              options=options)

                else:
                    Utils.push_info(feedback, f"WARNING: Layer: {src_layer.name()} is not vector ==> Not transferred")
            else:
                Utils.push_info(feedback, f"WARNING: Layer: {src_layer.name()} is not spatial ==> transferred")

    @staticmethod
    def set_layer_data_source(ctl_file, feedback):

        def _set_layer():

            qgs_project = QgsProject.instance()
            # Use the newly created GPKG file to set the data source of the QGIS project file
            provider_options = QgsDataProvider.ProviderOptions()
            provider_options.transformContext = qgs_project.transformContext()
            # Loop over each layer
            for i, src_layer in enumerate(qgs_project.mapLayers().values()):
                if src_layer.type() == QgsMapLayer.VectorLayer:
                    # Only process vector layer
                    if src_layer.type() == QgsMapLayer.VectorLayer:

                        qgs_layer_name = src_layer.name()
                        gpkg_layer_name = DDR_INFO.get_layer_short_name(src_layer)
                        uri = QgsProviderRegistry.instance().encodeUri('ogr',
                                                                       {'path': ctl_file.gpkg_file_name,
                                                                        'layerName': gpkg_layer_name})
                        src_layer.setDataSource(uri, qgs_layer_name, "ogr", provider_options)

        qgs_project = QgsProject.instance()
        _set_layer()
        qgs_project.write(ctl_file.out_qgs_project_file_en)
        qgs_project.clear()
        if ctl_file.qgis_project_file_fr  != "":
            qgs_project.read(ctl_file.out_qgs_project_file_fr)
            _set_layer()
            qgs_project.write(ctl_file.out_qgs_project_file_fr)


    @staticmethod
    def create_zip_file(ctl_file, feedback):
        """Create the zip file in the working directory"""

        # Change working directory to the temporary directory
        current_dir = os.getcwd()  # Save current directory
        os.chdir(ctl_file.control_file_dir)

        # Create the zip file with the 4 files
        lst_file_to_zip = [Path(ctl_file.control_file_name).name,
                           Path(ctl_file.gpkg_file_name).name,
                           Path(ctl_file.out_qgs_project_file_en).name,
                           Path(ctl_file.out_qgs_project_file_fr).name]
        ctl_file.zip_file_name = os.path.join(ctl_file.control_file_dir, "ddr_publish.zip")
        Utils.push_info(feedback, f"INFO: Creating the zip file: {ctl_file.zip_file_name}")
        with zipfile.ZipFile(ctl_file.zip_file_name, mode="w") as archive:
            for file_to_zip in lst_file_to_zip:
                archive.write(file_to_zip)

        # Reset to the current directory
        os.chdir(current_dir)

    @staticmethod
    def restore_original_project_file(ctl_file, feedback):
        """Restore the original project file"""

        qgs_project = QgsProject.instance()

        # Reopen the original project file
        Utils.push_info(feedback, f"INFO: Restoring original project file (.qgs): {ctl_file.src_qgs_project_name}")
        qgs_project.read(ctl_file.src_qgs_project_name)

    @staticmethod
    def delete_dir_file(ctl_file, feedback):
        """Delete the temporary directory and files"""

        if ctl_file.keep_files == "No":
            # Delete the temporary directory and all its content
            for dummy in range(5):
                # Sometimes the delete does work the first time so we have to retry the file being busy...
                try:
                    shutil.rmtree(ctl_file.control_file_dir)
                    Utils.push_info(feedback, f"INFO: Deleting temporary directory and content: {ctl_file.control_file_dir}")
                    break
                except Exception:
                    # Wait a little bit... to resolve synchronicity problem
                    time.sleep(.5)

    @staticmethod
    def push_info(feedback, message, suppl="", pad_with_dot=False):
        """This method formats and logs the message in the processing toolbox log"""

        str_date_time = Utils.get_date_time()
        suppl = str(suppl)  # Make sure the "text" to display is a string
        lines = suppl.split("\n")  # If the message is on many lines print many lines
        for line in lines:
            if pad_with_dot:
                leading_sp = len(line) - len(line.lstrip())  # Extract the number of leading spaces
                line = line.replace(line[0:leading_sp], "." * leading_sp)  # Replace leading spaces by "." (dots)
            feedback.pushInfo(f"{str_date_time} - {str(message)}{line}")


class UtilsGui():
    """Contains a list of static methods"""

    HELP_USAGE = """
        <b>Usage</b>
        <u>Select the English QGIS project file (.qgs)</u>: Select the project file with the ENGLISH layer description.
        <u>Select the French QGIS project file (.qgs)</u>: Select the project file with the French layer description.
        <u>Select the department</u>: Select which department own the publication.
        <u>Enter the metadata UUID</u>: Enter the UUID associated to this UUID.
        <u>Select the CSZ theme</u>: Select the theme under which the project will be published in the clip ship zip (CSZ)
        <b>Advanced Parameters</b>
        <u>Enter your email address</u>: Email address used to send publication notification.
        <u>Select the download info ID</u>: Download ID info (no choice).
        <u>Select the QGIS server</u>: Name of the QGIS server used for the publication (no choice).
        <u>Keep temporary files (for debug purpose)</u> : Flag (Yes/No) for keeping/deleting temporary files.
    """

    @staticmethod
    def add_login(self):
        """Add Login menu"""

        self.addParameter(
            QgsProcessingParameterAuthConfig('AUTHENTICATION', 'Authentication Configuration', defaultValue=None))

    @staticmethod
    def add_qgis_file(self):
        """Add Select EN and FR project file menu"""

        self.addParameter(
            QgsProcessingParameterFile(
                name='QGIS_FILE_EN',
                description=' Select the English QGIS project file (.qgs)',
                extension='qgs',
                behavior=QgsProcessingParameterFile.File))

        self.addParameter(
            QgsProcessingParameterFile(
                name='QGIS_FILE_FR',
                description=' Select the French QGIS project file (.qgs)',
                extension='qgs',
                behavior=QgsProcessingParameterFile.File))

    @staticmethod
    def add_department(self):
        """Add Select depertment menu"""

        self.addParameter(QgsProcessingParameterEnum(
            name='DEPARTMENT',
            description=self.tr("Select the department"),
            options=DDR_INFO.get_department_lst(),
            defaultValue="nrcan",
            usesStaticStrings=True,
            allowMultiple=False))

    @staticmethod
    def add_uuid(self):
        """Add Select UUID menu"""

        import uuid
        idd = ""
#        idd = uuid.uuid4()
        self.addParameter(QgsProcessingParameterString(
            name="METADATA_UUID",
            defaultValue=str(idd),
            description=self.tr('Enter the metadata UUID')))

    @staticmethod
    def add_download_info(self):
        """Add Select download info menu"""

        lst_download_info_id = ["DDR_DOWNLOAD1"]
        parameter = QgsProcessingParameterEnum(
            name='DOWNLOAD_INFO_ID',
            description=self.tr("Select the download info ID"),
            options=lst_download_info_id,
            defaultValue=lst_download_info_id[0],
            usesStaticStrings=True,
            allowMultiple=False)
        parameter.setFlags(parameter.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(parameter)

    @staticmethod
    def add_email(self):
        """Add Select email menu"""

        parameter = QgsProcessingParameterString(
            name="EMAIL",
            defaultValue=str(DDR_INFO.get_email()),
            description=self.tr('Enter your email address'))
        parameter.setFlags(parameter.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(parameter)

    @staticmethod
    def add_qgs_server_id(self):
        """Add Select server menu"""

        lst_qgs_server_id = ['DDR_QGS1']
        parameter = QgsProcessingParameterEnum(
            name='QGS_SERVER_ID',
            description=self.tr('Select the QGIS server'),
            options=lst_qgs_server_id,
            defaultValue=lst_qgs_server_id[0],
            usesStaticStrings=True,
            allowMultiple=False)
        parameter.setFlags(parameter.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(parameter)

    @staticmethod
    def add_csz_themes(self):
        """Add Select themes menu"""

        self.addParameter(QgsProcessingParameterEnum(
            name='CSZ_THEMES',
            description=self.tr("Select the theme under which you want to publish your project in the clip-zip-ship (CZS)"),
            options=[""] + DDR_INFO.get_theme_lst("en"),
            usesStaticStrings=True,
            allowMultiple=False,
            optional=True))

    @staticmethod
    def add_keep_files(self):
        """Add Keep file menu"""

        lst_flag = ['Yes', 'No']
        parameter = QgsProcessingParameterEnum(
            name='KEEP_FILES',
            description=self.tr('Keep temporary files (for debug purpose)'),
            options=lst_flag,
            defaultValue=lst_flag[1],
            usesStaticStrings=True,
            allowMultiple=False)
        parameter.setFlags(parameter.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(parameter)

    @staticmethod
    def read_parameters(self, ctl_file, parameters, context, feedback):

        ctl_file.department = self.parameterAsString(parameters, 'DEPARTMENT', context)
        ctl_file.download_info_id = self.parameterAsString(parameters, 'DOWNLOAD_INFO_ID', context)
        ctl_file.metadata_uuid = self.parameterAsString(parameters, 'METADATA_UUID', context)
        ctl_file.email = self.parameterAsString(parameters, 'EMAIL', context)
        ctl_file.qgs_server_id = self.parameterAsString(parameters, 'QGS_SERVER_ID', context)
        ctl_file.keep_files = self.parameterAsString(parameters, 'KEEP_FILES', context)
        ctl_file.csz_collection_theme = self.parameterAsString(parameters, 'CSZ_THEMES', context)
        ctl_file.qgis_project_file_en = self.parameterAsString(parameters, 'QGIS_FILE_EN', context)
        ctl_file.qgis_project_file_fr = self.parameterAsString(parameters, 'QGIS_FILE_FR', context)


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
        return 'Management (second step)'

    def flags(self):
        """Return the flags setting the NoThreading very important otherwise there are weird bugs...
        """

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

        UtilsGui.add_qgis_file(self)
        UtilsGui.add_department(self)
        UtilsGui.add_uuid(self)
        UtilsGui.add_csz_themes(self)
        UtilsGui.add_email(self)
        UtilsGui.add_download_info(self)
        UtilsGui.add_qgs_server_id(self)
        UtilsGui.add_keep_files(self)

    def read_parameters(self, ctl_file, parameters, context, feedback):
        """Reads the different parameters in the form and stores the content in the data structure"""

        UtilsGui.read_parameters(self, ctl_file, parameters, context, feedback)

        return

    @staticmethod
    def publish_project_file(ctl_file, parameters, context, feedback):
        """"""

        url = 'https://qgis.ddr-stage.services.geo.ca/api/processes'
        headers = {'accept': 'application/json',
                   'Authorization': 'Bearer ' + LOGIN_TOKEN.get_token(feedback)}
        files = {'zip_file': open(ctl_file.zip_file_name, 'rb')}

        Utils.push_info(feedback, f"INFO: Publishing to DDR")
        Utils.push_info(feedback, f"INFO: HTTP Put Request: {url}")
        Utils.push_info(feedback, f"INFO: HTTP Headers: {str(headers)}")
        Utils.push_info(feedback, f"INFO: Zip file to publish: {ctl_file.zip_file_name}")
        Utils.push_info(feedback, f"INFO: HTTP Put Request: {url}")
        try:
            response = requests.put(url, files=files, verify=False, headers=headers)
            ResponseCodes.publish_project_file(feedback, response)

        except requests.exceptions.RequestException as e:
            raise UserMessageException(f"Major problem with the DDR Publication API: {url}")

        return

    def processAlgorithm(self, parameters, context, feedback):
        """Main method that extract parameters and call Simplify algorithm.
        """

        try:
            Utils.process_algorithm(self, "PUBLISH", parameters, context, feedback)
        except UserMessageException as e:
            Utils.push_info(feedback, f"ERROR: Publish process")
            Utils.push_info(feedback, f"ERROR: {str(e)}")

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
        return 'Management (second step)'

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

        UtilsGui.add_qgis_file(self)
        UtilsGui.add_department(self)
        UtilsGui.add_uuid(self)
        UtilsGui.add_csz_themes(self)
        UtilsGui.add_email(self)
        UtilsGui.add_download_info(self)
        UtilsGui.add_qgs_server_id(self)
        UtilsGui.add_keep_files(self)

    def read_parameters(self, ctl_file, parameters, context, feedback):
        """Reads the different parameters in the form and stores the content in the data structure"""

        UtilsGui.read_parameters(self, ctl_file, parameters, context, feedback)

        return

    @staticmethod
    def validate_project_file(ctl_file, parameters, context, feedback):
        """"""

#        import web_pdb; web_pdb.set_trace()
        url = 'https://qgis.ddr-stage.services.geo.ca/api/validate'
        headers = {'accept': 'application/json',
                   'charset': 'utf-8',
                   'Authorization': 'Bearer ' + LOGIN_TOKEN.get_token(feedback)}
        files = {'zip_file': open(ctl_file.zip_file_name, 'rb')}

        Utils.push_info(feedback, "INFO: Validating project")
        Utils.push_info(feedback, "INFO: HTTP Headers: ", headers)
        Utils.push_info(feedback, "INFO: Zip file to publish: ", ctl_file.zip_file_name)

        try:
            Utils.push_info(feedback, "INFO: HTTP Post Request: ", url)
            response = requests.post(url, files=files, verify=False, headers=headers)
            ResponseCodes.validate_project_file(feedback, response)

        except requests.exceptions.RequestException as e:
            raise UserMessageException(f"Major problem with the DDR Publication API: {url}")
        return

    def processAlgorithm(self, parameters, context, feedback):
        """Main method that extract parameters and call Simplify algorithm.
        """

        try:
            Utils.process_algorithm(self, "VALIDATE", parameters, context, feedback)
        except UserMessageException as e:
            Utils.push_info(feedback, f"ERROR: Validate process")
            Utils.push_info(feedback, f"ERROR: {str(e)}")

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
        return 'Management (second step)'

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

        UtilsGui.add_qgis_file(self)
        UtilsGui.add_department(self)
        UtilsGui.add_uuid(self)
        UtilsGui.add_csz_themes(self)
        UtilsGui.add_email(self)
        UtilsGui.add_download_info(self)
        UtilsGui.add_qgs_server_id(self)
        UtilsGui.add_keep_files(self)

    def read_parameters(self, ctl_file, parameters, context, feedback):
        """Reads the different parameters in the form and stores the content in the data structure"""

        UtilsGui.read_parameters(self, ctl_file, parameters, context, feedback)

        return

    @staticmethod
    def unpublish_project_file(ctl_file, parameters, context, feedback):
        """Unpublish a QGIS project file """

        url = 'https://qgis.ddr-stage.services.geo.ca/api/processes'
        headers = {'accept': 'application/json',
                   'Authorization': 'Bearer ' + LOGIN_TOKEN.get_token(feedback)}
        files = {'zip_file': open(ctl_file.zip_file_name, 'rb')}
        Utils.push_info(feedback, f"INFO: Publishing to DDR")
        Utils.push_info(feedback, f"INFO: HTTP Delete Request: {url}")
        Utils.push_info(feedback, f"INFO: HTTP Headers: {str(headers)}")
        Utils.push_info(feedback, f"INFO: Zip file to publish: {ctl_file.zip_file_name}")

        try:
            response = requests.delete(url, files=files, verify=False, headers=headers)
            ResponseCodes.unpublish_project_file(feedback, response)

        except requests.exceptions.RequestException as e:
            raise UserMessageException(f"Major problem with the DDR Publication API: {url}")

        return

    def processAlgorithm(self, parameters, context, feedback):
        """Main method that extract parameters and call Simplify algorithm.
        """
        try:
            Utils.process_algorithm(self, "UNPUBLISH", parameters, context, feedback)
        except UserMessageException as e:
            Utils.push_info(feedback, f"ERROR: Unpublish process")
            Utils.push_info(feedback, f"ERROR: {str(e)}")

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
        help_str = """This processing plugin logins in the DDR repository server. The authentication operation is \
        mandatory before  doing any management operation: publication, unpublication or validation. 
        """

        help_str = help_str + UtilsGui.HELP_USAGE

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

        UtilsGui.add_login(self)

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
            raise UserMessageException("Unable to extract username/password from QGIS "
                                       "authentication system")

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
#            import web_pdb;  web_pdb.set_trace()
            Utils.read_ddr_departments(ctl_file, feedback)

#            import web_pdb; web_pdb.set_trace()
            Utils.read_user_email(ctl_file, feedback)

        except UserMessageException as e:
            Utils.push_info(feedback, f"ERROR: Login process")
            Utils.push_info(feedback, f"ERROR: {str(e)}")

        return {}
