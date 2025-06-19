Deploying the Publish MDM Helm Chart
====================================

This guide will walk you through deploying the Publish MDM Helm Chart on a Kubernetes cluster.


1. Create a Kubernetes Cluster
------------------------------

You can create a Kubernetes cluster on your preferred platform. In this guide we will use Amazon EKS.

Prerequisites:

- AWS CLI installed and configured.
- ``eksctl`` installed.
- AWS IAM user or role with necessary permissions.

**Note:** You can test your IAM user by running an AWS command, such as ``aws s3 ls``.

You may test the cluster creation by running the command below, which will output all the cluster specifications:

.. code-block:: shell

    eksctl create cluster \
        --name=publish-mdm \
        --region=us-east-1 \
        --node-type=t3a.medium \
        --nodes=2 \
        --with-oidc \
        --version=1.32 \
        --dry-run

To actually create the cluster:

.. code-block:: shell

    eksctl create cluster \
        --name=publish-mdm \
        --region=us-east-1 \
        --node-type=t3a.medium \
        --nodes=2 \
        --with-oidc \
        --version=1.32

You'll know the creation process finished successfully when the command line prompt returns and you see a message along the lines of::

    2025-04-15 11:19:29 [✔]  created 1 managed nodegroup(s) in cluster "publish-mdm"
    2025-04-15 11:19:30 [ℹ]  kubectl command should work with "/Users/ronardluna/.kube/config", try 'kubectl get nodes'
    2025-04-15 11:19:30 [✔]  EKS cluster "publish-mdm" in "us-east-1" region is ready

**Note:** It's good always to specify the node type, otherwise AWS will default to massive nodes.

Your new cluster should be “Active” in EKS. You can add it to you Kubernetes config with:

.. code-block:: shell

    aws eks --region us-east-1 update-kubeconfig --name publish-mdm

From EKS 1.23 onwards, a `Container Storage Interface (CSI) driver <https://kubernetes.io/blog/2019/01/15/container-storage-interface-ga/>`_
is needed to get your PersistentVolumeClaims served by a PersistentVolume
(`see here for more info <https://stackoverflow.com/questions/75758115/persistentvolumeclaim-is-stuck-waiting-for-a-volume-to-be-created-either-by-ex>`_).
If you need to use a PersitentVolume you’ll need to add the Amazon VPC CNI add-on.
`Colin Copeland’s post <https://www.caktusgroup.com/blog/2023/05/03/update-amazon-eks-cluster-kubernetes-version-123/>`_ can help you add it to your cluster.

2. Install Dependencies
-----------------------

You'll install the following dependencies using `Helm <https://helm.sh/docs/intro/install/>`_ charts:

- `Nginx Ingress Controller <https://github.com/kubernetes/ingress-nginx>`_
- `Cert Manager <https://cert-manager.io/>`_
- `PostgreSQL <https://github.com/bitnami/charts/tree/main/bitnami/postgresql>`_ (optional).

2.1. Installing the Nginx Ingress Controller
++++++++++++++++++++++++++++++++++++++++++++

First add its repository to Helm:

.. code-block:: shell

    helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
    helm repo update

Run the following command to install the Nginx Ingress Controller, name the Helm release "nginx-ingress", and set the ``publishService`` parameter to ``true``:

.. code-block:: shell

    helm install nginx-ingress ingress-nginx/ingress-nginx \
        --set controller.publishService.enabled=true

Run this command to watch the Load Balancer become available:

.. code-block:: shell

    kubectl --namespace default get services \
        -o wide \
        -w nginx-ingress-ingress-nginx-controller

While waiting for the Load Balancer to become available, the above command will show ``<pending>`` in the ``EXTERNAL-IP`` column.

Next, you'll need to ensure that your domain is pointed to the Load Balancer via your domain's A record. This should be done through your DNS provider.

2.2. Installing Cert-Manager
++++++++++++++++++++++++++++

To secure your Ingress Resources, you'll install Cert-Manager, which you'll use to provision TLS certificates for the cluster.

Then add the `Jetstack Helm repository <https://charts.jetstack.io/>`_ to Helm, which hosts the Cert-Manager chart:

.. code-block:: shell

    helm repo add jetstack https://charts.jetstack.io
    helm repo update

Finally, install Cert-Manager into the cert-manager namespace. We'll also set the ``crds.enabled`` parameter to ``true``
in order to install cert-manager ``CustomResourceDefinition`` manifests:

.. code-block:: shell

    helm install cert-manager jetstack/cert-manager \
        --namespace cert-manager \
        --create-namespace \
        --set crds.enabled=true

Next, you need to set up an Issuer to issue TLS certificates. To create one that issues
Let's Encrypt certificates, create a file named ``production_issuer.yaml`` with these contents
(replace ``your_email_address`` with your email address to receive any notices regarding your certificates):

.. code-block:: yaml

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

Apply the configuration:

.. code-block:: shell

    kubectl apply -f production_issuer.yaml

2.3. Installing a PostgreSQL Helm Chart
+++++++++++++++++++++++++++++++++++++++

.. note::

    You can skip this step if your PostgreSQL database will not be hosted in your Kubernetes cluster
    (e.g. if you've set up your PostgreSQL database in another server or you're using a
    managed service like Amazon RDS or DigitalOcean Managed Database).

To host the PostgreSQL database within your cluster, you can install the
`PostgreSQL Helm Chart from Bitnami <https://github.com/bitnami/charts/tree/main/bitnami/postgresql>`_.

As mentioned earlier, you will need to have the Amazon EBS CSI driver installed in your cluster
to use Persistent Volumes. If you haven't done so already, you can install it using `eksctl`:

.. code-block:: shell

    # Create the role and service account for the EBS CSI driver
    eksctl create iamserviceaccount \
        --name ebs-csi-controller-sa \
        --namespace kube-system \
        --cluster publish-mdm \
        --region us-east-1 \
        --role-name AmazonEKS_EBS_CSI_DriverRole \
        --role-only \
        --attach-policy-arn arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy \
        --approve

    # Install the EBS CSI driver addon
    export AWS_ACCOUNT_ID=$(aws sts get-caller-identity | jq --raw-output ".Account")
    eksctl create addon \
        --cluster publish-mdm \
        --region us-east-1 \
        --name aws-ebs-csi-driver \
        --service-account-role-arn arn:aws:iam::${AWS_ACCOUNT_ID}:role/AmazonEKS_EBS_CSI_DriverRole \
        --force

And create the StorageClass that will be used for the Persistent Volumes in ``sc.yaml``:

.. code-block:: yaml

    apiVersion: storage.k8s.io/v1
    kind: StorageClass
    metadata:
        name: auto-ebs-sc
        annotations:
            storageclass.kubernetes.io/is-default-class: "true"
    provisioner: ebs.csi.eks.amazonaws.com
    volumeBindingMode: WaitForFirstConsumer
    parameters:
        type: gp3
        encrypted: "true"

Apply the StorageClass configuration:

.. code-block:: shell

    kubectl apply -f sc.yaml

Next, add the Bitnami repository:

.. code-block:: shell

    helm repo add bitnami https://charts.bitnami.com/bitnami
    helm repo update

Then install the Helm chart within the namespace you created. We will install version 15.5.38 as it's
the last version that supports PostgreSQL 16 and the Publish MDM Docker container currently does not work well
with PostgreSQL 17. You can update the ``auth.*`` values below as necessary,
and set any `other parameters <https://github.com/bitnami/charts/tree/main/bitnami/postgresql#parameters>`_ you may need:

.. code-block:: shell

    helm install publish-mdm-db bitnami/postgresql --version 15.5.38 \
        --namespace publish-mdm-db \
        --create-namespace \
        --set global.defaultStorageClass=auto-ebs-sc \
        --set persistence.storageClass=auto-ebs-sc \
        --set auth.database=publish_mdm \
        --set auth.password=A3Or4uW2vIPoZfJF \
        --set auth.username=publish_mdm \
        --set auth.postgresPassword=9eCFAO8Tte3eyLBq

**Note:** On some platforms, you may need to set the ``global.defaultStorageClass`` value to
specify the StorageClass to be used for Persistent Volumes. To see the available
storage classes in your cluster, run ``kubectl get storageclass``.

The output of the ``helm install`` command will include the domain name for accessing PostgreSQL
from within the cluster. (e.g. ``publish-mdm-db-postgresql.publish-mdm-db.svc.cluster.local``). You will
use this domain name -- along with the ``auth.username``, ``auth.password``, and ``auth.database``
values from above -- to create the ``DATABASE_URL`` environment variable in the next section.

3. Installing the Publish MDM Helm Chart
----------------------------------------

Now you'll install Publish MDM using its `Helm chart <https://github.com/caktus/helm-charts/tree/main/charts/publish-mdm>`_.

Then add the `Caktus repository <https://caktus.github.io/helm-charts>`_ to Helm:

.. code-block:: shell

    helm repo add caktus https://caktus.github.io/helm-charts
    helm repo update

Create a file named ``chart_values.yaml`` with your values for the Helm chart.
All the possible values are documented in the `README file for the Helm chart <https://github.com/caktus/helm-charts/blob/main/charts/publish-mdm/README.md#configuration>`_.
Below is a sample ``chart_values.yaml`` file that will create only one deployment for both WSGI and ASGI. Replace ``your_domain_name`` and update ``environmentVariables`` appropriately:

.. code-block:: yaml

    publish-mdm:
      publishDomain: your_domain_name
      image:
        tag: main
      environmentVariables:
        ADMIN_EMAIL: XXXXXXXXX
        ALLOWED_HOSTS: your_domain_name
        AWS_ACCESS_KEY_ID: XXXXXXXXX
        AWS_SECRET_ACCESS_KEY: XXXXXXXXX
        AWS_STORAGE_BUCKET_NAME: XXXXXXXXX
        DATABASE_URL: postgresql://postgres:postgres@172.17.0.1:9062/publish_mdm
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
          secretName: publish-mdm-tls

Finally, install Publish MDM into the namespace you created earlier, using the values from the ``chart_values.yaml`` file to override the Helm chart's default values:

.. code-block:: shell

    helm install publish-mdm caktus/publish-mdm \
        -f chart_values.yaml \
        --namespace publish-mdm \
        --create-namespace

Confirm if all the necessary resources have been created successfully:

.. code-block:: shell

    kubectl get all -n publish-mdm

That's it! The Publish MDM web application should now be available at ``https://your_domain_name``

Next Steps
----------

A few next steps you may want to consider:
- Create and configure S3 buckets for media and static files.
- Configure Infisical for managing secrets and environment variables.
