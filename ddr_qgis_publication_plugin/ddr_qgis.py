# If you are not inside a QGIS console you first need to import
# qgis and PyQt classes you will use in this script as shown below

import sys, os, threading
import urllib.parse, psycopg2
from psycopg2 import sql
from qgis.core import QgsApplication, QgsProject, QgsCoordinateReferenceSystem, QgsVectorLayerExporter, QgsVectorDataProvider


# Constant
data_provider_key = "postgres"


def _gen_base_uri(host: str, port: int, db_name: str, user: str, password: str, ssl_mode: bool):
	return f"host='{host}' port={str(port)} dbname='{db_name}' user='{user}' password='{password}' sslmode={str(ssl_mode)}"


def _formatLayerName(layer_name):
	# Format database table name
	return layer_name.replace(" ", "_").lower()


class DdrPyQgis(object):
	def __init__(self, qgis_install_path, qgis_project_file, qgis_db_host, qgis_db_port, qgis_db_name,
				 qgis_db_user, qgis_db_password, qgis_db_ssl_mode, qgis_db_schema):
		# QGIS props
		print("__init__ 1")
		print(threading.current_thread())

		self.qgis_app_reference = QgsApplication([], False)

		print("__init__ 2")
		self.set_qgis_path = QgsApplication.setPrefixPath(qgis_install_path, True)

		print("__init__ 3")
		self.init_qgis = self.qgis_app_reference.initQgis()
		self.qgis_project_file = qgis_project_file
		self.project = QgsProject.instance()
		self.project.read(self.qgis_project_file)

		# Database props
		self.qgis_db_host = qgis_db_host
		self.qgis_db_port = qgis_db_port
		self.qgis_db_name = qgis_db_name
		self.qgis_db_user = qgis_db_user
		self.qgis_db_password = qgis_db_password
		self.qgis_db_ssl_mode = qgis_db_ssl_mode
		self.qgis_db_schema = qgis_db_schema


	def close(self):
		# remove the provider and layer registries from memory
		self.qgis_app_reference.exitQgis()


	def open_conn(self):
		"""
		Connects to the database.

		:returns: A :class:`~psycopg2` connection
		"""

		# Connects and returns the connection
		return psycopg2.connect(host=self.qgis_db_host, port=self.qgis_db_port, dbname=self.qgis_db_name, user=self.qgis_db_user, password=self.qgis_db_password)


	def gen_uri_export(self, schema, table, type):
		# Redirect
		uri = _gen_base_uri(self.qgis_db_host, self.qgis_db_port, self.qgis_db_name,
							self.qgis_db_user, self.qgis_db_password, self.qgis_db_ssl_mode)
		return uri + f" table=\"{schema}\".\"{table}\" key='fid' type={type}"


	def gen_uri_data_source(self, schema, table, type, srid):
		uri = self.gen_uri_export(schema, table, type)
		return uri + f" checkPrimaryKeyUnicity='{1}' srid={srid} estimatedmetadata=true"


	def gen_uri_project(self, filename):
		return f"postgresql://{urllib.parse.quote(self.qgis_db_user)}:{urllib.parse.quote(self.qgis_db_password)}@{self.qgis_db_host}:{self.qgis_db_port}?dbname={self.qgis_db_name}&schema={self.qgis_db_schema}&project={filename}"


	def exportLayersInDB(self):
		try:
			for layer in self.project.mapLayers().values():
				# Get layer Projection
				layer_crs = layer.dataProvider().crs().authid()[5:]

				# Get layer Geometry Type
				geom_type = layer.geometryType()

				# Generate the uri
				uri = self.gen_uri_export(self.qgis_db_schema, _formatLayerName(layer.name() + " (geom)"), geom_type)

				# Build the ReferenceSystem object
				dest_crs = QgsCoordinateReferenceSystem("EPSG:" + layer_crs)

				# Export the layer in DDR Postgres DB
				error, message = QgsVectorLayerExporter.exportLayer(layer, uri, data_provider_key, dest_crs)

				# If success
				if error == 0:
					print("The Layer " + layer.name() + " has been exported in the DDR Postgres DB")
					return True

				else:
					print("An Error Occured in exportLayersInDB : " + message)

		except Exception as ex:
			print("ERROR in method exportLayersInDB()")
			print(ex)

		return False


	def removeLayersFromDB(self):
		try:
			for layer in self.project.mapLayers().values():
				# Connect to the database
				with self.open_conn() as conn:
					# Open a cursor
					with conn.cursor() as cur:
						# The drop query
						str_query = "DROP TABLE {table};"

						# Query in the database
						query = sql.SQL(str_query).format(
							table=sql.Identifier(self.qgis_db_schema, _formatLayerName(layer.name() + " (geom)")))

						# Execute cursor
						cur.execute(query)

				print("Table dropped from database")
				return True

		except Exception as ex:
			print("ERROR in method removeLayersFromDB()")
			print(ex)

		return False


	def setLayersDataSource(self):
		# Set Layer Data Source to new Postgres location
		try:
			for layer in self.project.mapLayers().values():
				# Get layer Projection
				layer_crs = layer.dataProvider().crs().authid()[5:]

				# Get layer Geometry Type
				geom_type = layer.geometryType()

				# Generate the uri
				uri = self.gen_uri_data_source(self.qgis_db_schema, _formatLayerName(layer.name() + " (geom)"), geom_type, layer_crs)

				# Go
				layer.setDataSource(uri, layer.name(), data_provider_key)

				print("The Layer " + layer.name() + " data source has been changed in the QGIS project file")
				return True

		except Exception as ex:
			print("ERROR in method setLayersDataSource()")
			print(ex)

		return False


	def saveLayerStyleInDB(self, layer):
		# Save layer style to DDR Pastgres DB
		try:
			style_name = self.qgis_db_schema+"_"+_formatLayerName(layer.name())
			styles = layer.listStylesInDatabase()[2]

			# If style already exists in the DDR DB, we overwrite it (delete/save)
			if style_name in styles:
				#print('style exists')
				#style_id = layer.listStylesInDatabase()[1][styles.index(style_name)]

				# Save style
				layer.saveStyleToDatabase(style_name, "Default style for {}".format(layer.name()), True, "")
				print('Style "' + style_name + '" has been updated in the DDR Database')

			else:
				#print('style does not exist')
				layer.saveStyleToDatabase(style_name, "Default style for {}".format(layer.name()), True, "")
				print('Style "' + style_name + '" has been added in the DDR Database')

			return True

		except Exception as ex:
			print("ERROR in method saveLayerStyleInDB()")
			print(ex)

		return False


	def deleteLayerStyleFromDB(self, layer):
		# Save layer style to DDR Pastgres DB
		try:
			styles = layer.listStylesInDatabase()[2]
			style_id = layer.listStylesInDatabase()[1][styles.index(_formatLayerName(layer.name()))]

			#style_name = self.qgis_db_schema+"_"+_formatLayerName(layer.name())

			# Delete style
			error, message = layer.deleteStyleFromDatabase(style_id)

			# If success
			if error == 0:
				print("Style has been deleted in the DDR Database")
				return True

			else:
				print("An Error Occured in deleteLayerStyleFromDB : " + message)

		except Exception as ex:
			print("ERROR in method deleteLayerStyleFromDB()")
			print(ex)

		return False


	def saveProjectInDB(self):
		try:
			# Get the filename
			filename = os.path.basename(self.qgis_project_file).split(".")[0]

			# Generate the uri
			uri = self.gen_uri_project(filename)

			# Save the QGIS project in DDR Postgres DB
			saved = self.project.write(uri)

			if saved:
				print("The QGIS Project " + filename + " has been saved in the DDR Postgres DB")
				# Get the storage
				#storage = QgsApplication.projectStorageRegistry().projectStorageFromUri(uri)
				#print(storage.listProjects(uri))
				return True

			else:
				print("Failed to save the QGIS Project " + filename + " in the db.")


		except Exception as ex:
			print("ERROR in method saveProjectInDB()")
			print(ex)

		return False


	def deleteProjectFromDB(self):
		try:
			# Get the filename
			filename = os.path.basename(self.qgis_project_file).split(".")[0]

			# Generate the uri
			uri = self.gen_uri_project(filename)

			# Get the storage
			storage = QgsApplication.projectStorageRegistry().projectStorageFromUri(uri)
			#print(storage.listProjects(uri))

			#if not storage:
			#	storage = self.project.read(uri)

			# If found
			if storage:
				# Delete the QGIS project from DDR Postgres DB
				deleted = storage.removeProject(uri)

				if deleted:
					print("The QGIS Project " + filename + " has been deleted from the DDR Postgres DB")
					return True

				else:
					print("Failed to delete the GIS Project " + filename + " from the storage")

			else:
				print("Failed to retrieve storage for the QGIS Project " + filename)

		except Exception as ex:
			print("ERROR in method deleteProjectFromDB()")
			print(ex)

		return False


