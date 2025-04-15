Deploying the ODK Publish Helm Chart
====================================

This guide will walk you through deploying the ODK Publish Helm Chart on a Kubernetes cluster.


1. Create a Kubernetes cluster
------------------------------
...


2. Install Dependencies
-----------------------

You’ll install the following dependencies using `Helm <https://helm.sh/docs/intro/install/>`_ charts:

- `Nginx Ingress Controller <https://github.com/kubernetes/ingress-nginx>`_
- `Cert Manager <https://cert-manager.io/>`_
- PostgreSQL (optional).

2.1. Installing the Kubernetes Nginx Ingress Controller
+++++++++++++++++++++++++++++++++++++++++++++++++++++++

First add its repository to Helm::

    helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
    helm repo update

Run the following command to install the Nginx Ingress Controller, name the Helm release "nginx-ingress", and set the ``publishService`` parameter to ``true``::

    helm install nginx-ingress ingress-nginx/ingress-nginx --set controller.publishService.enabled=true

Run this command to watch the Load Balancer become available::

    kubectl --namespace default get services -o wide -w nginx-ingress-ingress-nginx-controller

While waiting for the Load Balancer to become available, the above command will show ``<pending>`` in the ``EXTERNAL-IP`` column.

Next, you’ll need to ensure that your domain is pointed to the Load Balancer via your domain's A record. This should be done through your DNS provider.

2.2. Installing Cert-Manager
++++++++++++++++++++++++++++

To secure your Ingress Resources, you’ll install Cert-Manager, which you'll use to provision TLS certificates for the cluster.

First, create a namespace for it::

    kubectl create namespace cert-manager

Then add the `Jetstack Helm repository <https://charts.jetstack.io/>`_ to Helm, which hosts the Cert-Manager chart::

    helm repo add jetstack https://charts.jetstack.io
    helm repo update

Finally, install Cert-Manager into the cert-manager namespace. We'll also set the ``crds.enabled`` parameter to ``true``
in order to install cert-manager ``CustomResourceDefinition`` manifests::

    helm install cert-manager jetstack/cert-manager --namespace cert-manager --set crds.enabled=true

Next, you need to set up an Issuer to issue TLS certificates. To create one that issues
Let’s Encrypt certificates, create a file named ``production_issuer.yaml`` with these contents
(replace ``your_email_address`` with your email address to receive any notices regarding your certificates)::

    apiVersion: cert-manager.io/v1
    kind: ClusterIssuer
    metadata:
      name: letsencrypt-prod
    spec:
      acme:
        # Email address used for ACME registration
        email: your_email_address
        server: https://acme-v02.api.letsencrypt.org/directory
        privateKeySecretRef:
          # Name of a secret used to store the ACME account private key
          name: letsencrypt-prod-private-key
        # Add a single challenge solver, HTTP01 using nginx
        solvers:
        - http01:
            ingress:
              class: nginx

Apply the configuration::

    kubectl apply -f production_issuer.yaml


2.3. Installing a PostgreSQL Helm Chart
+++++++++++++++++++++++++++++++++++++++

.. note::

    You can skip this step if your PostgreSQL database will not be hosted in your Kubernetes cluster
    (e.g. if you've set up your PostgreSQL database in another server or you're using a managed service like Amazon RDS or DigitalOcean Managed Database).

...


3. Installing the ODK Publish Helm Chart
----------------------------------------

Now you'll install ODK Publish using its `Helm chart <https://github.com/caktus/helm-charts/tree/main/charts/odk-publish>`_.

First, create a namespace for it::

    kubectl create namespace odk-publish

Then add the `Caktus repository <https://caktus.github.io/helm-charts>`_ to Helm::

    helm repo add caktus https://caktus.github.io/helm-charts
    helm repo update

Create a file named ``chart_values.yaml`` with your values for the Helm chart.
All the possible values are documented in the `README file for the Helm chart <https://github.com/caktus/helm-charts/blob/main/charts/odk-publish/README.md#configuration>`_.
Below is a sample ``chart_values.yaml`` file that will create only one deployment for both WSGI and ASGI. Replace ``your_domain_name`` and update ``environmentVariables`` appropriately::

    odk-publish:
      publishDomain: your_domain_name
      image:
        tag: main
      environmentVariables:
        ADMIN_EMAIL: XXXXXXXXX
        ALLOWED_HOSTS: your_domain_name
        AWS_ACCESS_KEY_ID: XXXXXXXXX
        AWS_SECRET_ACCESS_KEY: XXXXXXXXX
        AWS_STORAGE_BUCKET_NAME: XXXXXXXXX
        DATABASE_URL: postgresql://postgres:postgres@172.17.0.1:9062/odk_publish
        DEFAULT_FILE_STORAGE: config.storages.MediaBoto3Storage
        DEFAULT_FROM_EMAIL: XXXXXXXXX
        DJANGO_MANAGEPY_MIGRATE: 'on'
        DJANGO_SECRET_KEY: XXXXXXXXX
        DJANGO_SECURE_SSL_REDIRECT: 'True'
        EMAIL_BACKEND: django.core.mail.backends.smtp.EmailBackend
        EMAIL_HOST: XXXXXXXXX
        EMAIL_HOST_PASSWORD: XXXXXXXXX
        EMAIL_HOST_USER: XXXXXXXXX
        EMAIL_USE_TLS: 'true'
        ENVIRONMENT: XXXXXXXXX
        GOOGLE_CLIENT_ID: XXXXXXXXX
        GOOGLE_CLIENT_SECRET: XXXXXXXXX
        GOOGLE_API_KEY: XXXXXXXXX
        GOOGLE_APP_ID: XXXXXXXXX
        NEW_RELIC_APP_NAME: XXXXXXXXX
        NEW_RELIC_ENVIRONMENT: XXXXXXXXX
        NEW_RELIC_LICENSE_KEY: XXXXXXXXX
        ODK_CENTRAL_CREDENTIALS: XXXXXXXXX
        SENTRY_DSN: XXXXXXXXX
      ingress:
        annotations:
          cert-manager.io/cluster-issuer: letsencrypt-prod
          kubernetes.io/ingress.class: nginx
          nginx.ingress.kubernetes.io/proxy-body-size: 100m
          nginx.org/mergeable-ingress-type: master
        className: nginx
        enabled: true
        hosts:
        - host: your_domain_name
          paths:
          - path: /
            pathType: ImplementationSpecific
        tls:
        - hosts:
          - your_domain_name
          secretName: odk-publish-tls

Finally, install ODK Publish into the namespace you created earlier, using the values from the ``chart_values.yaml`` file to override the Helm chart's default values::

    helm install odk-publish caktus/odk-publish -f chart_values.yaml --namespace odk-publish

Confirm if all the necessary resources have been created successfully::

    kubectl get all -n odk-publish

That's it! Your ODK Publish instance should now be available at ``https://your_domain_name``
