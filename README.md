<!-- omit in toc -->

# ODK Publish

This repository contains the proof-of-concept ODK Publish project.

## Development

1. Configure your environment:

      ```sh
      layout python python3.12
      use node 22
  
      export DJANGO_SETTINGS_MODULE=config.settings.dev
  
      # postgres
      export PGHOST=localhost
      export PGPORT=5432
      export PGUSER=$USER
      export PGDATABASE=odk_publish
      export DATABASE_URL=postgresql://$PGUSER@$PGHOST:$PGPORT/$PGDATABASE
      export DATABASE_URL_SQLALCHEMY=postgresql+psycopg://$PGUSER@$PGHOST:$PGPORT/$PGDATABASE
  
      # google oauth for django-allauth
      export GOOGLE_CLIENT_ID=
      export GOOGLE_CLIENT_SECRET=
  
      # odk central
      export ODK_CENTRAL_USERNAME=
      export ODK_CENTRAL_PASSWORD=
      ```

2. Install the required dependencies.

      ```sh
      make setup
      npm install
      ```

3. Setup the database.

      ```sh
      python manage.py migrate
      python manage.py populate_sample_odk_data
      ```

4. Run the development server.

      ```sh
      # in one terminal
      npm run dev
      # in another terminal
      python manage.py runserver
      ```
