clean:
	@find . -name "*.pyc" -exec rm -rf {} \;
	@find . -name "__pycache__" -delete

reset_app:
	python manage.py migrate $(name) zero
	rm apps/$(name)/migrations/00*
	python manage.py makemigrations $(name)
	python manage.py migrate
