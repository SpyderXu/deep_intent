from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import hickle as hkl
import numpy as np
from tensorflow.python.pywrap_tensorflow import do_quantize_training_on_graphdef

np.random.seed(9 ** 10)
from keras import backend as K
K.set_image_dim_ordering('tf')
from keras import regularizers
from keras.layers import Dropout
from keras.models import Sequential
from keras.layers.core import Activation
from keras.utils.vis_utils import plot_model
from keras.initializers import RandomNormal
from keras.layers.wrappers import TimeDistributed
from keras.layers.convolutional import Conv2D
from keras.layers.convolutional import Conv2DTranspose
from keras.layers.convolutional import Conv3D
from keras.layers.convolutional import Conv3DTranspose
from keras.layers.convolutional import UpSampling3D
from keras.layers.convolutional_recurrent import ConvLSTM2D
from keras.layers.merge import multiply
from keras.layers.merge import add
from keras.layers.merge import concatenate
from keras.layers.core import Permute
from keras.layers.core import RepeatVector
from keras.layers.core import Dense
from keras.layers.core import Lambda
from keras.layers.core import Reshape
from keras.layers.core import Flatten
from keras.layers.recurrent import LSTM
from keras.layers.recurrent import GRU
from keras.layers.normalization import BatchNormalization
from keras.callbacks import LearningRateScheduler
from keras.layers.advanced_activations import LeakyReLU
from keras.layers import Input
from keras.models import Model
from custom_layers import AttnLossLayer
from experience_memory import ExperienceMemory
from config_r10 import *
from sys import stdout

import tb_callback
import lrs_callback
import argparse
import math
import cv2
import os


def encoder_model():
    model = Sequential()

    # 10x128x128
    model.add(Conv3D(filters=128,
                     strides=(1, 4, 4),
                     kernel_size=(3, 11, 11),
                     padding='same',
                     input_shape=(int(VIDEO_LENGTH/2), 128, 208, 3)))
    model.add(TimeDistributed(BatchNormalization()))
    model.add(TimeDistributed(LeakyReLU(alpha=0.2)))
    model.add(TimeDistributed(Dropout(0.5)))

    # 10x32x32
    model.add(Conv3D(filters=64,
                     strides=(1, 2, 2),
                     kernel_size=(3, 5, 5),
                     padding='same'))
    model.add(TimeDistributed(BatchNormalization()))
    model.add(TimeDistributed(LeakyReLU(alpha=0.2)))
    model.add(TimeDistributed(Dropout(0.5)))

    # 10x16x16
    model.add(Conv3D(filters=64,
                     strides=(1, 1, 1),
                     kernel_size=(3, 3, 3),
                     padding='same'))
    model.add(TimeDistributed(BatchNormalization()))
    model.add(TimeDistributed(LeakyReLU(alpha=0.2)))
    model.add(TimeDistributed(Dropout(0.5)))

    return model


def decoder_model():
    inputs = Input(shape=(int(VIDEO_LENGTH/2), 16, 26, 64))

    # 10x16x16
    convlstm_1 = ConvLSTM2D(filters=128,
                            kernel_size=(3, 3),
                            strides=(1, 1),
                            padding='same',
                            return_sequences=True,
                            recurrent_dropout=0.2)(inputs)
    x = TimeDistributed(BatchNormalization())(convlstm_1)
    out_1 = TimeDistributed(Activation('tanh'))(x)
    # x = TimeDistributed(LeakyReLU(alpha=0.2))(x)

    convlstm_2 = ConvLSTM2D(filters=128,
                            kernel_size=(3, 3),
                            strides=(1, 1),
                            padding='same',
                            return_sequences=True,
                            recurrent_dropout=0.2)(out_1)
    x = TimeDistributed(BatchNormalization())(convlstm_2)
    out_2 = TimeDistributed(Activation('tanh'))(x)
    # h_2 = TimeDistributed(LeakyReLU(alpha=0.2))(x)
    # out_2 = UpSampling3D(size=(1, 2, 2))(h_2)

    res_1 = add([out_1, out_2])
    res_1 = UpSampling3D(size=(1, 2, 2))(res_1)

    # 10x32x32
    convlstm_3a = ConvLSTM2D(filters=64,
                            kernel_size=(3, 3),
                            strides=(1, 1),
                            padding='same',
                            return_sequences=True,
                            recurrent_dropout=0.2)(res_1)
    x = TimeDistributed(BatchNormalization())(convlstm_3a)
    out_3a = TimeDistributed(Activation('tanh'))(x)
    # h_3 = TimeDistributed(LeakyReLU(alpha=0.2))(x)
    # out_3a = UpSampling3D(size=(1, 2, 2))(h_3)

    convlstm_3b = ConvLSTM2D(filters=64,
                            kernel_size=(3, 3),
                            strides=(1, 1),
                            padding='same',
                            return_sequences=True,
                            recurrent_dropout=0.2)(out_3a)
    x = TimeDistributed(BatchNormalization())(convlstm_3b)
    out_3b = TimeDistributed(Activation('tanh'))(x)
    # h_3 = TimeDistributed(LeakyReLU(alpha=0.2))(x)
    # out_3 = UpSampling3D(size=(1, 2, 2))(h_3)

    res_2 = add([out_3a, out_3b])
    res_2 = UpSampling3D(size=(1, 2, 2))(res_2)

    # 10x64x64
    convlstm_4a = ConvLSTM2D(filters=16,
                            kernel_size=(3, 3),
                            strides=(1, 1),
                            padding='same',
                            return_sequences=True,
                            recurrent_dropout=0.2)(res_2)
    x = TimeDistributed(BatchNormalization())(convlstm_4a)
    out_4a = TimeDistributed(Activation('tanh'))(x)
    # h_4 = TimeDistributed(LeakyReLU(alpha=0.2))(x)

    convlstm_4b = ConvLSTM2D(filters=16,
                            kernel_size=(3, 3),
                            strides=(1, 1),
                            padding='same',
                            return_sequences=True,
                            recurrent_dropout=0.2)(out_4a)
    x = TimeDistributed(BatchNormalization())(convlstm_4b)
    out_4b = TimeDistributed(Activation('tanh'))(x)
    # h_4 = TimeDistributed(LeakyReLU(alpha=0.2))(x)

    res_3 = add([out_4a, out_4b])
    res_3 = UpSampling3D(size=(1, 2, 2))(res_3)

    # 10x128x128
    convlstm_5 = ConvLSTM2D(filters=3,
                            kernel_size=(3, 3),
                            strides=(1, 1),
                            padding='same',
                            return_sequences=True,
                            recurrent_dropout=0.2)(res_3)
    predictions = TimeDistributed(Activation('tanh'))(convlstm_5)

    model = Model(inputs=inputs, outputs=predictions)

    return model


def set_trainability(model, trainable):
    model.trainable = trainable
    for layer in model.layers:
        layer.trainable = trainable


def autoencoder_model(encoder, decoder):
    model = Sequential()
    model.add(encoder)
    model.add(decoder)
    return model


def arrange_images(video_stack):
    n_frames = video_stack.shape[0] * video_stack.shape[1]
    frames = np.zeros((n_frames,) + video_stack.shape[2:], dtype=video_stack.dtype)

    frame_index = 0
    for i in range(video_stack.shape[0]):
        for j in range(video_stack.shape[1]):
            frames[frame_index] = video_stack[i, j]
            frame_index += 1

    img_height = video_stack.shape[2]
    img_width = video_stack.shape[3]
    # width = img_size x video_length
    width = img_width * video_stack.shape[1]
    # height = img_size x batch_size
    height = img_height * BATCH_SIZE
    shape = frames.shape[1:]
    image = np.zeros((height, width, shape[2]), dtype=video_stack.dtype)
    frame_number = 0
    for i in range(BATCH_SIZE):
        for j in range(video_stack.shape[1]):
            image[(i * img_height):((i + 1) * img_height), (j * img_width):((j + 1) * img_width)] = frames[frame_number]
            frame_number = frame_number + 1

    return image


def load_weights(weights_file, model):
    model.load_weights(weights_file)


def run_utilities(encoder, decoder, autoencoder, ENC_WEIGHTS, DEC_WEIGHTS):
    if PRINT_MODEL_SUMMARY:
        print (encoder.summary())
        print (decoder.summary())
        print (autoencoder.summary())
        # exit(0)

    # Save model to file
    if SAVE_MODEL:
        print ("Saving models to file...")
        model_json = encoder.to_json()
        with open(os.path.join(MODEL_DIR, "encoder.json"), "w") as json_file:
            json_file.write(model_json)

        model_json = decoder.to_json()
        with open(os.path.join(MODEL_DIR, "decoder.json"), "w") as json_file:
            json_file.write(model_json)

        model_json = autoencoder.to_json()
        with open(os.path.join(MODEL_DIR, "autoencoder.json"), "w") as json_file:
            json_file.write(model_json)

        if PLOT_MODEL:
            plot_model(encoder, to_file=os.path.join(MODEL_DIR, 'encoder.png'), show_shapes=True)
            plot_model(decoder, to_file=os.path.join(MODEL_DIR, 'decoder.png'), show_shapes=True)
            plot_model(autoencoder, to_file=os.path.join(MODEL_DIR, 'autoencoder.png'), show_shapes=True)

    if ENC_WEIGHTS != "None":
        print ("Pre-loading encoder with weights...")
        load_weights(ENC_WEIGHTS, encoder)
    if DEC_WEIGHTS != "None":
        print ("Pre-loading decoder with weights...")
        load_weights(DEC_WEIGHTS, decoder)


def load_to_RAM(frames_source):
    frames = np.zeros(shape=((len(frames_source),) + IMG_SIZE))
    print ("Decimating RAM!")
    j = 1
    for i in range(1, len(frames_source)):
        filename = "frame_" + str(j) + ".png"
        im_file = os.path.join(DATA_DIR, filename)
        try:
            frame = cv2.imread(im_file, cv2.IMREAD_COLOR)
            # frame = cv2.resize(frame, (112, 112), interpolation=cv2.INTER_CUBIC)
            frames[i] = (frame.astype(np.float32) - 127.5) / 127.5
            j = j + 1
        except AttributeError as e:
            print(im_file)
            print(e)

    return frames


def load_X_RAM(videos_list, index, frames):
    X = []
    for i in range(BATCH_SIZE):
        start_index = videos_list[(index*BATCH_SIZE + i), 0]
        end_index = videos_list[(index*BATCH_SIZE + i), -1]
        X.append(frames[start_index:end_index+1])
    X = np.asarray(X)

    return X


def load_X(videos_list, index, data_dir, img_size):
    X = np.zeros((BATCH_SIZE, VIDEO_LENGTH,) + img_size)
    for i in range(BATCH_SIZE):
        for j in range(VIDEO_LENGTH):
            filename = "frame_" + str(videos_list[(index*BATCH_SIZE + i), j]) + ".png"
            im_file = os.path.join(data_dir, filename)
            try:
                frame = cv2.imread(im_file, cv2.IMREAD_COLOR)
                # frame = cv2.resize(frame, (112, 112), interpolation=cv2.INTER_LANCZOS4)
                X[i, j] = (frame.astype(np.float32) - 127.5) / 127.5
            except AttributeError as e:
                print (im_file)
                print (e)

    return X


def get_video_lists(frames_source, stride):
    # Build video progressions
    videos_list = []
    start_frame_index = 1
    end_frame_index = VIDEO_LENGTH + 1
    while (end_frame_index <= len(frames_source)):
        frame_list = frames_source[start_frame_index:end_frame_index]
        if (len(set(frame_list)) == 1):
            videos_list.append(range(start_frame_index, end_frame_index))
            start_frame_index = start_frame_index + stride
            end_frame_index = end_frame_index + stride
        else:
            start_frame_index = end_frame_index - 1
            end_frame_index = start_frame_index + VIDEO_LENGTH

    videos_list = np.asarray(videos_list, dtype=np.int32)

    return np.asarray(videos_list)


def train(BATCH_SIZE, ENC_WEIGHTS, DEC_WEIGHTS):
    print ("Loading data definitions...")
    frames_source = hkl.load(os.path.join(DATA_DIR, 'sources_train_208.hkl'))
    videos_list = get_video_lists(frames_source=frames_source, stride=4)
    n_videos = videos_list.shape[0]

    # Setup test
    test_frames_source = hkl.load(os.path.join(TEST_DATA_DIR, 'sources_test_208.hkl'))
    test_videos_list = get_video_lists(frames_source=test_frames_source, stride=(int(VIDEO_LENGTH/2)))
    n_test_videos = test_videos_list.shape[0]

    if RAM_DECIMATE:
        frames = load_to_RAM(frames_source=frames_source)

    if SHUFFLE:
        # Shuffle images to aid generalization
        videos_list = np.random.permutation(videos_list)

    # Build the Spatio-temporal Autoencoder
    print ("Creating models...")
    encoder = encoder_model()
    print (encoder.summary())

    decoder = decoder_model()
    autoencoder = autoencoder_model(encoder, decoder)
    autoencoder.compile(loss="mean_absolute_error", optimizer=OPTIM_A)

    # Build attention layer output
    # intermediate_decoder = Model(inputs=decoder.layers[0].input, outputs=decoder.layers[10].output)
    # mask_gen_1 = Sequential()
    # mask_gen_1.add(encoder)
    # mask_gen_1.add(intermediate_decoder)
    # mask_gen_1.compile(loss='mean_squared_error', optimizer=OPTIM_A)

    run_utilities(encoder, decoder, autoencoder, ENC_WEIGHTS, DEC_WEIGHTS)

    NB_ITERATIONS = int(n_videos/BATCH_SIZE)
    # NB_ITERATIONS = 5
    NB_TEST_ITERATIONS = int(n_test_videos / BATCH_SIZE)

    # Setup TensorBoard Callback
    TC = tb_callback.TensorBoard(log_dir=TF_LOG_DIR, histogram_freq=0, write_graph=False, write_images=False)
    LRS = lrs_callback.LearningRateScheduler(schedule=schedule)
    LRS.set_model(autoencoder)

    print ("Beginning Training...")
    # Begin Training
    for epoch in range(NB_EPOCHS_AUTOENCODER):
        print("\n\nEpoch ", epoch)
        loss = []
        test_loss = []

        # Set learning rate every epoch
        LRS.on_epoch_begin(epoch=epoch)
        lr = K.get_value(autoencoder.optimizer.lr)
        print ("Learning rate: " + str(lr))

        for index in range(NB_ITERATIONS):
            # Train Autoencoder
            if RAM_DECIMATE:
                X = load_X_RAM(videos_list, index, frames)
            else:
                X = load_X(videos_list, index, DATA_DIR, IMG_SIZE)
            X_train = X[:, 0 : int(VIDEO_LENGTH/2)]
            y_train = X[:, int(VIDEO_LENGTH/2) :]
            loss.append(autoencoder.train_on_batch(X_train, y_train))

            arrow = int(index / (NB_ITERATIONS / 40))
            stdout.write("\rIter: " + str(index) + "/" + str(NB_ITERATIONS-1) + "  " +
                         "loss: " + str(loss[len(loss)-1]) +
                         "\t    [" + "{0}>".format("="*(arrow)))
            stdout.flush()

        if SAVE_GENERATED_IMAGES:
            # Save generated images to file
            predicted_images = autoencoder.predict(X_train, verbose=0)
            voila = np.concatenate((X_train, y_train), axis=1)
            truth_seq = arrange_images(voila)
            pred_seq = arrange_images(np.concatenate((X_train, predicted_images), axis=1))

            truth_seq = truth_seq * 127.5 + 127.5
            pred_seq = pred_seq * 127.5 + 127.5

            cv2.imwrite(os.path.join(GEN_IMAGES_DIR, str(epoch) + "_" + str(index) + "_truth.png"), truth_seq)
            cv2.imwrite(os.path.join(GEN_IMAGES_DIR, str(epoch) + "_" + str(index) + "_pred.png"), pred_seq)

        # Run over test data
        print ('')
        for index in range(NB_TEST_ITERATIONS):
            X = load_X(test_videos_list, index, TEST_DATA_DIR, IMG_SIZE)
            X_train = X[:, 0: int(VIDEO_LENGTH / 2)]
            y_train = X[:, int(VIDEO_LENGTH / 2):]
            test_loss.append(autoencoder.test_on_batch(X_train, y_train))

            arrow = int(index / (NB_TEST_ITERATIONS / 40))
            stdout.write("\rIter: " + str(index) + "/" + str(NB_TEST_ITERATIONS - 1) + "  " +
                         "test_loss: " + str(test_loss[len(test_loss) - 1]) +
                         "\t    [" + "{0}>".format("=" * (arrow)))
            stdout.flush()

        # then after each epoch/iteration
        avg_loss = sum(loss)/len(loss)
        avg_test_loss = sum(test_loss) / len(test_loss)
        logs = {'loss': avg_loss, 'test_loss': avg_test_loss}
        TC.on_epoch_end(epoch, logs)

        # Log the losses
        with open(os.path.join(LOG_DIR, 'losses.json'), 'a') as log_file:
            log_file.write("{\"epoch\":%d, \"loss\":%f, \"test_loss\":%f};\n" % (epoch, avg_loss, avg_test_loss))

            print("\nAvg loss: " + str(avg_loss) + " Avg test loss: " + str(avg_test_loss))

        # Save model weights per epoch to file
        encoder.save_weights(os.path.join(CHECKPOINT_DIR, 'encoder_epoch_' + str(epoch) + '.h5'), True)
        decoder.save_weights(os.path.join(CHECKPOINT_DIR, 'decoder_epoch_' + str(epoch) + '.h5'), True)

        # Save predicted attention mask per epoch
        # predicted_attn = mask_gen_1.predict(X_train, verbose=0)
        # a_pred = np.reshape(predicted_attn, newshape=(BATCH_SIZE, int(VIDEO_LENGTH/2), 16, 16, 1))
        # np.save(os.path.join(ATTN_WEIGHTS_DIR, 'attention_weights_gen1_' + str(epoch) + '.npy'), a_pred)

    # End TensorBoard Callback
    # TC.on_train_end('_')





def combine_images_test(X, y, generated_images):
    return arrange_images(X), arrange_images(y), arrange_images(generated_images)

def load_X_test(index, data_dir, img_size):
    X = np.zeros((BATCH_SIZE, VIDEO_LENGTH,) + img_size)
    for i in range(BATCH_SIZE):
        for j in range(1, VIDEO_LENGTH+1):
            file_num = str(int(((index*BATCH_SIZE*(VIDEO_LENGTH/2)) + (i*BATCH_SIZE) + j)))
            filename = file_num + ".png"
            im_file = os.path.join(data_dir, filename)
            try:
                frame = cv2.imread(im_file, cv2.IMREAD_COLOR)
                # frame = cv2.resize(frame, (112, 112), interpolation=cv2.INTER_LANCZOS4)
                X[i, j-1] = (frame.astype(np.float32) - 127.5) / 127.5
            except AttributeError as e:
                print (im_file)
                print (e)

    return X


def test(ENC_WEIGHTS, DEC_WEIGHTS):

    # Create models
    print ("Creating models...")
    encoder = encoder_model()
    decoder = decoder_model()
    autoencoder = autoencoder_model(encoder, decoder)


    if not os.path.exists(TEST_RESULTS_DIR + '/truth/'):
        os.mkdir(TEST_RESULTS_DIR + '/truth/')
    if not os.path.exists(TEST_RESULTS_DIR + '/pred/'):
        os.mkdir(TEST_RESULTS_DIR + '/pred/')

    def l1_l2_loss(y_true, y_pred):
        mse_loss = K.mean(K.square(y_pred - y_true), axis=-1)
        mae_loss = K.mean(K.abs(y_pred - y_true), axis=-1)

        return mse_loss + mae_loss

    run_utilities(encoder, decoder, autoencoder, ENC_WEIGHTS, DEC_WEIGHTS)
    autoencoder.compile(loss='mean_absolute_error', optimizer=OPTIM_A)

    # Setup test
    # test_frames_source = hkl.load(os.path.join(TEST_DATA_DIR, 'sources_test_128.hkl'))
    # test_videos_list = get_video_lists(frames_source=test_frames_source, stride=(VIDEO_LENGTH - 10))
    # n_test_videos = test_videos_list.shape[0]

    # NB_TEST_ITERATIONS = int(n_test_videos / BATCH_SIZE)
    path, dirs, files = os.walk(TEST_DATA_DIR).next()
    file_count = len(files)
    print (file_count)
    NB_TEST_ITERATIONS = int((file_count / int(VIDEO_LENGTH / 2)) / BATCH_SIZE)

    test_loss = []
    print (TEST_DATA_DIR)
    for index in range(NB_TEST_ITERATIONS):
        X = load_X_test(index, TEST_DATA_DIR, (128, 208, 3))
        X_train = X[:, 0: int(VIDEO_LENGTH / 2)]
        y_train = X[:, int(VIDEO_LENGTH / 2):]
        test_loss.append(autoencoder.test_on_batch(X_train, y_train))

        arrow = int(index / (NB_TEST_ITERATIONS / 40))
        stdout.write("\rIter: " + str(index) + "/" + str(NB_TEST_ITERATIONS - 1) + "  " +
                     "test_loss: " + str(test_loss[len(test_loss) - 1]) +
                     "\t    [" + "{0}>".format("=" * (arrow)))
        stdout.flush()

        if SAVE_GENERATED_IMAGES:
            # Save generated images to file
            predicted_images = autoencoder.predict(X_train, verbose=0)
            voila = np.concatenate((X_train, y_train), axis=1)
            truth_seq = arrange_images(voila)
            pred_seq = arrange_images(np.concatenate((X_train, predicted_images), axis=1))

            # orig_image, truth_image, pred_image = combine_images_test(X_train, y_train, predicted_images)
            # pred_image = pred_image * 127.5 + 127.5
            # orig_image = orig_image * 127.5 + 127.5
            # truth_image = truth_image * 127.5 + 127.5
            truth_seq = truth_seq * 127.5 + 127.5
            pred_seq = pred_seq * 127.5 + 127.5

            # cv2.imwrite(os.path.join(TEST_RESULTS_DIR + '/orig/', str(index) + "_orig.png"), orig_image)
            # cv2.imwrite(os.path.join(TEST_RESULTS_DIR + '/truth/', str(index) + "_truth.png"), truth_image)
            cv2.imwrite(os.path.join(TEST_RESULTS_DIR + '/truth/', str(index) + "_truth.png"), truth_seq)
            # cv2.imwrite(os.path.join(TEST_RESULTS_DIR + '/pred/', str(index) + "_pred.png"), pred_image)
            cv2.imwrite(os.path.join(TEST_RESULTS_DIR + '/pred/', str(index) + "_pred.png"), pred_seq)

    # then after each epoch/iteration
    avg_test_loss = sum(test_loss) / len(test_loss)

    # avg_loss = sum(loss) / len(loss)
    print("\nAvg loss: " + str(avg_test_loss))
    print("\n Std: " + str(np.std(np.asarray(test_loss))))
    print("\n Variance: " + str(np.var(np.asarray(test_loss))))
    print("\n Mean: " + str(np.mean(np.asarray(test_loss))))
    print("\n Max: " + str(np.max(np.asarray(test_loss))))
    print("\n Min: " + str(np.min(np.asarray(test_loss))))
    np.save(os.path.join(TEST_RESULTS_DIR, 'L1_loss.npy'), test_loss)


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", type=str)
    parser.add_argument("--enc_weights", type=str, default="None")
    parser.add_argument("--dec_weights", type=str, default="None")
    parser.add_argument("--gen_weights", type=str, default="None")
    parser.add_argument("--dis_weights", type=str, default="None")
    parser.add_argument("--batch_size", type=int, default=BATCH_SIZE)
    parser.add_argument("--nice", dest="nice", action="store_true")
    parser.set_defaults(nice=False)
    args = parser.parse_args()
    return args

if __name__ == "__main__":
    args = get_args()

    if args.mode == "train":
        train(BATCH_SIZE=args.batch_size,
              ENC_WEIGHTS=args.enc_weights,
              DEC_WEIGHTS=args.dec_weights)

    if args.mode == "test":
        test(ENC_WEIGHTS=args.enc_weights,
             DEC_WEIGHTS=args.dec_weights)