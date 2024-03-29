#!/usr/bin/env python
# coding: utf-8

# ## Breast Cancer Prediction
# *Predict Breast Cancer using SageMaker’s Linear-Learner with features derived from images of Breast Mass*

# ## Setup
# #The SageMaker role arn used to give learning and hosting access to your data. The snippet below will use the same role used by your SageMaker notebook instance, if you’re using other. Otherwise, specify the full ARN of a role with the SageMakerFullAccess policy attached.
# 
# The S3 bucket that you want to use for training and storing model objects.

# In[ ]:


import os
import boto3
import re
import sagemaker

role = sagemaker.get_execution_role()
region = boto3.Session().region_name

# S3 bucket for saving code and model artifacts.
# Feel free to specify a different bucket and prefix
bucket = sagemaker.Session().default_bucket()

prefix = 'sagemaker/DEMO-breast-cancer-prediction' # place to upload training files within the bucket



# In[19]:


#importing necessary libraries
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import io
import time
import json
import sagemaker.amazon.common as smac


# Data Source: https://archive.ics.uci.edu/ml/machine-learning-databases/breast-cancer-wisconsin/wdbc.data 
# 
# https://www.kaggle.com/uciml/breast-cancer-wisconsin-data
# 
# Let’s download the data and save it in the local folder with the name data.csv and take a look at it.

# In[20]:


data = pd.read_csv('https://archive.ics.uci.edu/ml/machine-learning-databases/breast-cancer-wisconsin/wdbc.data', header = None)

# specify columns extracted from wbdc.names
data.columns = ["id","diagnosis","radius_mean","texture_mean","perimeter_mean","area_mean","smoothness_mean",
                "compactness_mean","concavity_mean","concave points_mean","symmetry_mean","fractal_dimension_mean",
                "radius_se","texture_se","perimeter_se","area_se","smoothness_se","compactness_se","concavity_se",
                "concave points_se","symmetry_se","fractal_dimension_se","radius_worst","texture_worst",
                "perimeter_worst","area_worst","smoothness_worst","compactness_worst","concavity_worst",
                "concave points_worst","symmetry_worst","fractal_dimension_worst"]

# save the data
data.to_csv("data.csv", sep=',', index=False)

# print the shape of the data file
print(data.shape)

# show the top few rows
display(data.head())

# describe the data object
display(data.describe())

# we will also summarize the categorical field diganosis
display(data.diagnosis.value_counts())


# Key observations:
# Data has 569 observations and 32 columns.
# 
# First field is ‘id’.
# 
# Second field, ‘diagnosis’, is an indicator of the actual diagnosis (‘M’ = Malignant; ‘B’ = Benign).
# 
# There are 30 other numeric features available for prediction.

# # Create Features and Labels
# ## Split the data into 80% training, 10% validation and 10% testing

# In[21]:


rand_split = np.random.rand(len(data))
train_list = rand_split < 0.8
val_list = (rand_split >= 0.8) & (rand_split < 0.9)
test_list = rand_split >= 0.9

data_train = data[train_list]
data_val = data[val_list]
data_test = data[test_list]

train_y = ((data_train.iloc[:,1] == 'M') +0).to_numpy();
train_X = data_train.iloc[:,2:].to_numpy();

val_y = ((data_val.iloc[:,1] == 'M') +0).to_numpy();
val_X = data_val.iloc[:,2:].to_numpy();

test_y = ((data_test.iloc[:,1] == 'M') +0).to_numpy();
test_X = data_test.iloc[:,2:].to_numpy();


# Now, we’ll convert the datasets to the recordIO-wrapped protobuf format used by the Amazon SageMaker algorithms, 
# and then upload this data to S3. We’ll start with training data.

# In[22]:


train_file = 'linear_train.data'

f = io.BytesIO()
smac.write_numpy_to_dense_tensor(f, train_X.astype('float32'), train_y.astype('float32'))
f.seek(0)

boto3.Session().resource('s3').Bucket(bucket).Object(os.path.join(prefix, 'train', train_file)).upload_fileobj(f)


# Next we’ll convert and upload the validation dataset.

# In[23]:


validation_file = 'linear_validation.data'

f = io.BytesIO()
smac.write_numpy_to_dense_tensor(f, val_X.astype('float32'), val_y.astype('float32'))
f.seek(0)

boto3.Session().resource('s3').Bucket(bucket).Object(os.path.join(prefix, 'validation', validation_file)).upload_fileobj(f)


# # Train
# 
# Now we can begin to specify our linear model. Amazon SageMaker’s Linear Learner actually fits many models in parallel, each with slightly different hyperparameters, and then returns the one with the best fit. This functionality is automatically enabled. We can influence this using parameters like:
# 
# num_models to increase to total number of models run. The specified parameters will always be one of those models, but the algorithm also chooses models with nearby parameter values in order to find a solution nearby that may be more optimal. In this case, we’re going to use the max of 32.
# 
# loss which controls how we penalize mistakes in our model estimates. For this case, let’s use absolute loss as we haven’t spent much time cleaning the data, and absolute loss will be less sensitive to outliers.
# 
# wd or l1 which control regularization. Regularization can prevent model overfitting by preventing our estimates from becoming too finely tuned to the training data, which can actually hurt generalizability. In this case, we’ll leave these parameters as their default “auto” though.

# In[24]:


# See 'Algorithms Provided by Amazon SageMaker: Common Parameters' in the SageMaker documentation for an 
#explanation of these values.
from sagemaker.amazon.amazon_estimator import get_image_uri
container = get_image_uri(boto3.Session().region_name, 'linear-learner')


# In[25]:


linear_job = 'DEMO-linear-' + time.strftime("%Y-%m-%d-%H-%M-%S", time.gmtime())



print("Job name is:", linear_job)

linear_training_params = {
    "RoleArn": role,
    "TrainingJobName": linear_job,
    "AlgorithmSpecification": {
        "TrainingImage": container,
        "TrainingInputMode": "File"
    },
    "ResourceConfig": {
        "InstanceCount": 1,
        "InstanceType": "ml.c4.2xlarge",
        "VolumeSizeInGB": 10
    },
    "InputDataConfig": [
        {
            "ChannelName": "train",
            "DataSource": {
                "S3DataSource": {
                    "S3DataType": "S3Prefix",
                    "S3Uri": "s3://{}/{}/train/".format(bucket, prefix),
                    "S3DataDistributionType": "ShardedByS3Key"
                }
            },
            "CompressionType": "None",
            "RecordWrapperType": "None"
        },
        {
            "ChannelName": "validation",
            "DataSource": {
                "S3DataSource": {
                    "S3DataType": "S3Prefix",
                    "S3Uri": "s3://{}/{}/validation/".format(bucket, prefix),
                    "S3DataDistributionType": "FullyReplicated"
                }
            },
            "CompressionType": "None",
            "RecordWrapperType": "None"
        }

    ],
    "OutputDataConfig": {
        "S3OutputPath": "s3://{}/{}/".format(bucket, prefix)
    },
    "HyperParameters": {
        "feature_dim": "30",
        "mini_batch_size": "100",
        "predictor_type": "regressor",
        "epochs": "10",
        "num_models": "32",
        "loss": "absolute_loss"
    },
    "StoppingCondition": {
        "MaxRuntimeInSeconds": 60 * 60
    }
}


# Now let’s kick off our training job in SageMaker’s distributed, managed training, using the parameters we just created. Because training is managed, we don’t have to wait for our job to finish to continue, but for this case, let’s use boto3’s ‘training_job_completed_or_stopped’ waiter so we can ensure that the job has been started.

# In[26]:


get_ipython().run_cell_magic('time', '', "\nregion = boto3.Session().region_name\nsm = boto3.client('sagemaker')\n\nsm.create_training_job(**linear_training_params)\n\nstatus = sm.describe_training_job(TrainingJobName=linear_job)['TrainingJobStatus']\nprint(status)\nsm.get_waiter('training_job_completed_or_stopped').wait(TrainingJobName=linear_job)\nif status == 'Failed':\n    message = sm.describe_training_job(TrainingJobName=linear_job)['FailureReason']\n    print('Training failed with the following error: {}'.format(message))\n    raise Exception('Training job failed')\n")


# ## Host
# Now that we’ve trained the linear algorithm on our data, let’s setup a model which can later be hosted. We will: 1. Point to the scoring container 1. Point to the model.tar.gz that came from training 1. Create the hosting model

# In[27]:


linear_hosting_container = {
    'Image': container,
    'ModelDataUrl': sm.describe_training_job(TrainingJobName=linear_job)['ModelArtifacts']['S3ModelArtifacts']
}

create_model_response = sm.create_model(
    ModelName=linear_job,
    ExecutionRoleArn=role,
    PrimaryContainer=linear_hosting_container)

print(create_model_response['ModelArn'])


# Once we’ve setup a model, we can configure what our hosting endpoints should be. Here we specify: 1. EC2 instance type to use for hosting 1. Initial number of instances 1. Our hosting model name

# In[28]:


linear_endpoint_config = 'DEMO-linear-endpoint-config-' + time.strftime("%Y-%m-%d-%H-%M-%S", time.gmtime())
print(linear_endpoint_config)
create_endpoint_config_response = sm.create_endpoint_config(
    EndpointConfigName=linear_endpoint_config,
    ProductionVariants=[{
        'InstanceType': 'ml.m4.xlarge',
        'InitialInstanceCount': 1,
        'ModelName': linear_job,
        'VariantName': 'AllTraffic'}])

print("Endpoint Config Arn: " + create_endpoint_config_response['EndpointConfigArn'])


# Now that we’ve specified how our endpoint should be configured, we can create them. This can be done in the background, but for now let’s run a loop that updates us on the status of the endpoints so that we know when they are ready for use.

# In[ ]:


get_ipython().run_cell_magic('time', '', '\nlinear_endpoint = \'DEMO-linear-endpoint-\' + time.strftime("%Y%m%d%H%M", time.gmtime())\nprint(linear_endpoint)\ncreate_endpoint_response = sm.create_endpoint(\n    EndpointName=linear_endpoint,\n    EndpointConfigName=linear_endpoint_config)\nprint(create_endpoint_response[\'EndpointArn\'])\n\nresp = sm.describe_endpoint(EndpointName=linear_endpoint)\nstatus = resp[\'EndpointStatus\']\nprint("Status: " + status)\n\nsm.get_waiter(\'endpoint_in_service\').wait(EndpointName=linear_endpoint)\n\nresp = sm.describe_endpoint(EndpointName=linear_endpoint)\nstatus = resp[\'EndpointStatus\']\nprint("Arn: " + resp[\'EndpointArn\'])\nprint("Status: " + status)\n\nif status != \'InService\':\n    raise Exception(\'Endpoint creation did not succeed\')\n')


# ## Predict
# Now that we have our hosted endpoint, we can generate statistical predictions from it. Let’s predict on our test dataset to understand how accurate our model is.
# 
# There are many metrics to measure classification accuracy. Common examples include include: - Precision - Recall - F1 measure - Area under the ROC curve - AUC - Total Classification Accuracy - Mean Absolute Error
# 
# For our example, we’ll keep things simple and use total classification accuracy as our metric of choice. We will also evaluate Mean Absolute Error (MAE) as the linear-learner has been optimized using this metric, not necessarily because it is a relevant metric from an application point of view. We’ll compare the performance of the linear-learner against a naive benchmark prediction which uses majority class observed in the training data set for prediction on the test data.

# In[30]:


def np2csv(arr):
    csv = io.BytesIO()
    np.savetxt(csv, arr, delimiter=',', fmt='%g')
    return csv.getvalue().decode().rstrip()


# Next, we’ll invoke the endpoint to get predictions.

# In[31]:


runtime= boto3.client('runtime.sagemaker')

payload = np2csv(test_X)
response = runtime.invoke_endpoint(EndpointName=linear_endpoint,
                                   ContentType='text/csv',
                                   Body=payload)
result = json.loads(response['Body'].read().decode())
test_pred = np.array([r['score'] for r in result['predictions']])


# Let’s compare linear learner based mean absolute prediction errors from a baseline prediction which uses majority class to predict every instance.

# In[32]:


test_mae_linear = np.mean(np.abs(test_y - test_pred))
test_mae_baseline = np.mean(np.abs(test_y - np.median(train_y))) ## training median as baseline predictor

print("Test MAE Baseline :", round(test_mae_baseline, 3))
print("Test MAE Linear:", round(test_mae_linear,3))


# Let’s compare predictive accuracy using a classification threshold of 0.5 for the predicted and compare against the majority class prediction from training data set

# In[33]:


test_pred_class = (test_pred > 0.5)+0;
test_pred_baseline = np.repeat(np.median(train_y), len(test_y))

prediction_accuracy = np.mean((test_y == test_pred_class))*100
baseline_accuracy = np.mean((test_y == test_pred_baseline))*100

print("Prediction Accuracy:", round(prediction_accuracy,1), "%")
print("Baseline Accuracy:", round(baseline_accuracy,1), "%")


# Run the cell below to delete endpoint once you are done.

# In[ ]:


sm.delete_endpoint(EndpointName=linear_endpoint)

