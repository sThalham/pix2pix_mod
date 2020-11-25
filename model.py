from __future__ import print_function, division
import scipy

#from keras_contrib.layers.normalization import InstanceNormalization
from keras.layers import Input, Dense, Reshape, Flatten, Dropout, Concatenate, Subtract, Add
from keras.layers import BatchNormalization, Activation, ZeroPadding2D
from keras.layers.advanced_activations import LeakyReLU
from keras.activations import sigmoid
from keras.layers.convolutional import UpSampling2D, Conv2D
from keras.models import Sequential, Model, load_model
from keras.optimizers import Adam
import datetime
import sys
from data_loader import DataLoader
from pathlib import Path
import numpy as np
import os
import cv2
from glob import glob

from keras_contrib.applications import resnet
import keras_resnet
import keras_resnet.models


class default_model():
    def __init__(self, input_shape=(224, 224)):
        # Input shape
        self.img_rows = input_shape[0]
        self.img_cols = input_shape[1]
        self.channels = 3
        self.img_shape = (self.img_rows, self.img_cols, self.channels)

        optimizer = Adam(0.0002, 0.5)

        img_observed = Input(shape=self.img_shape)
        img_rendered = Input(shape=self.img_shape)
        img_da = Input(shape=self.img_shape)

        self.backbone_obs = self.resnet_no_top()
        print(self.backbone_obs)
        self.backbone_ren = self.resnet_no_top()
        estimator = self.build_generator()

        delta, aux_task = estimator([img_observed, img_rendered, img_da])

        self.model = Model(inputs=[img_observed, img_rendered, img_da], outputs=[delta, aux_task])
        print(self.model.summary())
        self.model.compile(loss=['mae', 'binary_crossentropy'], weights=[1, 1], optimizer=optimizer)

    def resnet_no_top(self):

        input = Input(shape=self.img_shape)
        resnet = keras_resnet.models.ResNet18(input, include_top=False, freeze_bn=True)

        outputs = self.PFPN(resnet.outputs[1], resnet.outputs[2], resnet.outputs[3])

        return Model(inputs=input, outputs=outputs)

    def PFPN(self, C3, C4, C5, feature_size=256):

        P3 = Conv2D(feature_size, kernel_size=1, strides=1, padding='same')(C3)
        P4 = Conv2D(feature_size, kernel_size=1, strides=1, padding='same')(C4)
        P5 = Conv2D(feature_size, kernel_size=1, strides=1, padding='same')(C5)

        P5_upsampled = UpSampling2D(size=2, interpolation="bilinear")(P5)
        P4_upsampled = UpSampling2D(size=2, interpolation="bilinear")(P4)
        P4_mid = Add()([P5_upsampled, P4])
        P4_mid = Conv2D(feature_size, kernel_size=3, strides=1, padding='same')(P4_mid)
        P3_mid = Add()([P4_upsampled, P3])sigmoid
        P3_mid = Conv2D(feature_size, kernel_size=3, strides=1, padding='same')(P3_mid)
        P3_down = Conv2D(feature_size, kernel_size=3, strides=2, padding='same')(P3_mid)
        #P3_fin = Add()([P3_mid, P3])
        #P3 = Conv2D(feature_size, kernel_size=3, strides=1, padding='same', name='P3')(P3_fin)

        P4_fin = Add()([P3_down, P4_mid])
        P4_down = Conv2D(feature_size, kernel_size=3, strides=2, padding='same')(P4_fin)
        #P4_fin = keras.layers.Add()([P4_fin, P4])  # skip connection
        #P4 = keras.layers.Conv2D(feature_size, kernel_size=3, strides=1, padding='same', name='P4')(P4_fin)

        P5_fin = Add()([P4_down, P5])
        P5 = Conv2D(feature_size, kernel_size=3, strides=1, padding='same', name='P5')(P5_fin)

        return P5

    def build_generator(self, pyramid_features=256, head_features=256):

        # Image input
        obs = Input(shape=self.img_shape)
        ren = Input(shape=self.img_shape)
        real = Input(shape=self.img_shape)

        model_obs = self.backbone_obs(obs)
        model_ren = self.backbone_ren(ren)

        diff = Subtract()([model_obs, model_ren])
        delta = Conv2D(4, kernel_size=3)(diff)

        da_obs = self.backbone_obs(real)
        da_ren = self.backbone_ren(real)
        da_out_obs = Conv2D(4, kernel_size=3)(da_obs)
        da_out_ren = Conv2D(4, kernel_size=3)(da_ren)
        da_act_obs = Activation('sigmoid')(da_out_obs)
        da_act_ren = Activation('sigmoid')(da_out_ren)
        da_out = Concatenate()([da_act_obs, da_act_ren])

        return Model(inputs=[obs, ren, real], outputs=[delta, da_out])
