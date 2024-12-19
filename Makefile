update_requirements:
	pip install -U -q pip-tools
	pip-compile --upgrade --strip-extras --output-file=requirements/base/base.txt requirements/base/base.in
	pip-compile --upgrade --strip-extras --output-file=requirements/dev/dev.txt requirements/dev/dev.in

install_requirements:
	@echo 'Installing pip-tools...'
	export PIP_REQUIRE_VIRTUALENV=true; \
	pip install -U -q pip-tools
	@echo 'Installing requirements...'
	pip-sync requirements/base/base.txt requirements/dev/dev.txt

setup:
	@echo 'Setting up the environment...'
	make install_requirements

clean:
	@find . -name "*.pyc" -exec rm -rf {} \;
	@find . -name "__pycache__" -delete

run-dev:
	@echo 'Running local development'
	docker-compose up -d --remove-orphans
	npm run dev &
	python manage.py runserver

run-tests:
	@echo 'Checking for migrations'
	python manage.py makemigrations --settings config.settings.test --dry-run | grep 'No changes detected' || (echo 'There are changes which require migrations.' && exit 1)
	pytest
