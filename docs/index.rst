.. ODK Publish documentation master file, created by
   sphinx-quickstart on Tue Feb 11 11:34:13 2025.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

ODK Publish
===========

ODK Publish is a proof-of-concept open-source tool to publish XLSForm templates
from Google Sheets to `ODK Central <https://getodk.org/>`_. It offers support
for single sign-on with Google, project template variables, and a user-friendly
interface for publishing form versions.


.. toctree::
   :maxdepth: 2
   :caption: Contents:

Test diagram:

.. mermaid::

   ---
   config:
      class:
         hideEmptyMembersBox: true
   ---
   classDiagram
      StaffForm_AppUser200 <|-- StaffForm
      StaffForm_AppUser100 <|-- StaffForm
      StaffForm_AppUser100 <|-- AppUser100
      StaffForm_AppUser200 <|-- AppUser200
      class StaffForm {
         center_name
         center_id
      }
      class AppUser100 {
         center_name = School
         center_id = 100
      }
      class AppUser200 {
         center_name = Library
         center_id = 200
      }
      class StaffForm_AppUser100 {
         center_name = School
         center_id = 100
      }
      class StaffForm_AppUser200 {
         center_name = Library
         center_id = 200
      }
