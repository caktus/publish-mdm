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

reset_app:
	python manage.py migrate $(name) zero
	rm apps/$(name)/migrations/00*
	python manage.py makemigrations $(name)
	python manage.py migrate
