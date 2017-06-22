from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from keras import backend as K
from keras.models import Sequential
from keras.layers import Dense
from keras.layers import Reshape
from keras.layers.core import Activation
from keras.layers.normalization import BatchNormalization
from keras.layers.convolutional import UpSampling2D
from keras.layers.convolutional import Conv2D, MaxPooling2D, Conv2DTranspose
from keras.layers.core import Flatten
from keras.optimizers import SGD
from keras.datasets import mnist
from data_utils import SequenceGenerator
from model_config import *
import numpy as np
np.random.seed(2 ** 10)
from PIL import Image
import argparse
import math
import os
K.set_image_dim_ordering('tf')

def generator_model():
    model = Sequential()
    model.add(Dense(input_dim=100, units=1024))
    model.add(Activation('tanh'))
    model.add(Dense(512*4*4))
    model.add(BatchNormalization())
    model.add(Activation('tanh'))
    model.add(Reshape((4, 4, 512), input_shape=(512*4*4,)))
    model.add(Conv2D(filters=512, kernel_size=(4,4), padding='same'))
    model.add(Conv2DTranspose(filters=256, kernel_size=(4, 4), strides=(2, 2), padding='same', activation='tanh'))
    model.add(Conv2DTranspose(filters=128, kernel_size=(4, 4), strides=(2, 2), padding='same', activation='tanh'))
    # model.add(Conv2DTranspose(filters=128, kernel_size=(4, 4), strides=(2, 2), padding='same', activation='tanh'))
    # model.add(UpSampling2D(size=(2, 2)))
    # model.add(Conv2D(filters=256, kernel_size=(4, 4), padding='same'))
    # model.add(Activation('tanh'))
    # model.add(UpSampling2D(size=(2, 2)))
    # model.add(Conv2D(filters=128, kernel_size=(4, 4), padding='same'))
    # model.add(Activation('tanh'))
    # model.add(UpSampling2D(size=(2, 2)))
    # model.add(Conv2D(filters=64, kernel_size=(4, 4), padding='same'))
    # model.add(Activation('tanh'))
    # model.add(UpSampling2D(size=(2, 2)))
    model.add(Conv2DTranspose(filters=64, kernel_size=(4,4), strides=(2,2), padding='same', activation='tanh'))
    model.add(Conv2DTranspose(filters=3, kernel_size=(4,4), strides=(2,2), padding='same', activation='tanh'))
    # model.add(Conv2D(filters=3, kernel_size=(4, 4), padding='same'))
    # model.add(Activation('tanh'))
    return model


def discriminator_model():
    model = Sequential()
    model.add(Conv2D(filters=64, kernel_size=(4, 4), padding='same', input_shape=(64, 64, 3)))
    model.add(BatchNormalization())
    model.add(Activation('tanh'))

    model.add(Conv2D(filters=64, kernel_size=(4, 4), strides=2, padding='same'))
    model.add(BatchNormalization())
    model.add(Activation('tanh'))
    model.add(Conv2D(filters=128, kernel_size=(4, 4), strides=2, padding='same'))
    model.add(BatchNormalization())
    model.add(Activation('tanh'))

    model.add(Conv2D(filters=256, kernel_size=(4, 4), strides=2, padding='same'))
    model.add(BatchNormalization())
    model.add(Activation('tanh'))

    model.add(Flatten())
    model.add(Dense(1024))
    model.add(Activation('tanh'))
    model.add(Dense(1))
    model.add(Activation('sigmoid'))
    return model


def generator_containing_discriminator(generator, discriminator):
    model = Sequential()
    model.add(generator)
    discriminator.trainable = False
    model.add(discriminator)
    return model


def combine_images(generated_images):
    num = generated_images.shape[0]
    width = int(math.sqrt(num))
    height = int(math.ceil(float(num)/width))
    shape = generated_images.shape[2:]
    image = np.zeros((height*shape[0], width*shape[1]),
                     dtype=generated_images.dtype)
    for index, img in enumerate(generated_images):
        i = int(index/width)
        j = index % width
        image[i*shape[0]:(i+1)*shape[0], j*shape[1]:(j+1)*shape[1]] = \
            img[0, :, :]
    return image


def load_data():
    # Data configuration:
    print ("Loading data...")

    train_file = os.path.join(DATA_DIR, 'X_train.hkl')
    train_sources = os.path.join(DATA_DIR, 'sources_train.hkl')
    val_file = os.path.join(DATA_DIR, 'X_val.hkl')
    val_sources = os.path.join(DATA_DIR, 'sources_val.hkl')

    train_generator = SequenceGenerator(train_file, train_sources, nt, batch_size=batch_size, shuffle=True)
    val_generator = SequenceGenerator(val_file, val_sources, nt, batch_size=batch_size, N_seq=N_seq_val)

    nb_classes = 10
    image_size = 32

    (X_train, y_train), (X_test, y_test) = cifar10.load_data()
    X_train = X_train.astype('float32')
    X_test = X_test.astype('float32')

    # convert class vectors to binary class matrices
    Y_train = np_utils.to_categorical(y_train, nb_classes)
    Y_test = np_utils.to_categorical(y_test, nb_classes)

    return X_train, Y_train, X_test, Y_test

def train(BATCH_SIZE):
    (X_train, y_train), (X_test, y_test) = mnist.load_data()
    X_train = (X_train.astype(np.float32) - 127.5)/127.5
    # X_train = X_train.reshape((X_train.shape[0], 1) + X_train.shape[1:])
    X_train = np.expand_dims(X_train, axis=3)
    discriminator = discriminator_model()
    generator = generator_model()
    # print (generator.summary())
    # print (discriminator.summary())
    # print (discriminator_on_generator.summary())
    # exit(0)

    discriminator_on_generator = generator_containing_discriminator(generator, discriminator)
    d_optim = SGD(lr=0.0005, momentum=0.9, nesterov=True)
    g_optim = SGD(lr=0.0005, momentum=0.9, nesterov=True)
    generator.compile(loss='binary_crossentropy', optimizer="SGD")
    discriminator_on_generator.compile(loss='binary_crossentropy', optimizer=g_optim)
    discriminator.trainable = True
    discriminator.compile(loss='binary_crossentropy', optimizer=d_optim)
    noise = np.zeros((BATCH_SIZE, 100))

    print (generator.summary())
    print (discriminator.summary())

    for epoch in range(100):
        print("Epoch is", epoch)
        print("Number of batches", int(X_train.shape[0]/BATCH_SIZE))
        for index in range(int(X_train.shape[0]/BATCH_SIZE)):
            for i in range(BATCH_SIZE):
                noise[i, :] = np.random.uniform(-1, 1, 100)
            image_batch = X_train[index*BATCH_SIZE:(index+1)*BATCH_SIZE]
            generated_images = generator.predict(noise, verbose=0)
            if index % 20 == 0:
                image = combine_images(generated_images)
                image = image*127.5+127.5
                Image.fromarray(image.astype(np.uint8)).save(
                    str(epoch)+"_"+str(index)+".png")
            X = np.concatenate((image_batch, generated_images))
            y = [1] * BATCH_SIZE + [0] * BATCH_SIZE
            d_loss = discriminator.train_on_batch(X, y)
            print("batch %d d_loss : %f" % (index, d_loss))
            for i in range(BATCH_SIZE):
                noise[i, :] = np.random.uniform(-1, 1, 100)
            discriminator.trainable = False
            g_loss = discriminator_on_generator.train_on_batch(
                noise, [1] * BATCH_SIZE)
            discriminator.trainable = True
            print("batch %d g_loss : %f" % (index, g_loss))
            if index % 10 == 9:
                generator.save_weights('generator', True)
                discriminator.save_weights('discriminator', True)


def generate(BATCH_SIZE, nice=False):
    generator = generator_model()
    generator.compile(loss='binary_crossentropy', optimizer="SGD")
    generator.load_weights('generator')
    if nice:
        discriminator = discriminator_model()
        discriminator.compile(loss='binary_crossentropy', optimizer="SGD")
        discriminator.load_weights('discriminator')
        noise = np.zeros((BATCH_SIZE*20, 100))
        for i in range(BATCH_SIZE*20):
            noise[i, :] = np.random.uniform(-1, 1, 100)
        generated_images = generator.predict(noise, verbose=1)
        d_pret = discriminator.predict(generated_images, verbose=1)
        index = np.arange(0, BATCH_SIZE*20)
        index.resize((BATCH_SIZE*20, 1))
        pre_with_index = list(np.append(d_pret, index, axis=1))
        pre_with_index.sort(key=lambda x: x[0], reverse=True)
        nice_images = np.zeros((BATCH_SIZE, 1) +
                               (generated_images.shape[2:]), dtype=np.float32)
        for i in range(int(BATCH_SIZE)):
            idx = int(pre_with_index[i][1])
            nice_images[i, 0, :, :] = generated_images[idx, 0, :, :]
        image = combine_images(nice_images)
    else:
        noise = np.zeros((BATCH_SIZE, 100))
        for i in range(BATCH_SIZE):
            noise[i, :] = np.random.uniform(-1, 1, 100)
        generated_images = generator.predict(noise, verbose=1)
        image = combine_images(generated_images)
    image = image*127.5+127.5
    Image.fromarray(image.astype(np.uint8)).save(
        "generated_image.png")


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", type=str)
    parser.add_argument("--batch_size", type=int, default=128)
    parser.add_argument("--nice", dest="nice", action="store_true")
    parser.set_defaults(nice=False)
    args = parser.parse_args()
    return args

if __name__ == "__main__":
    args = get_args()
    if args.mode == "train":
        train(BATCH_SIZE=args.batch_size)
    elif args.mode == "generate":
        generate(BATCH_SIZE=args.batch_size, nice=args.nice)