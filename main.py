""" NLP and DeapLearning course - Assignment 2
In this assignment we tried to classify clouds formation using a Single layer network
and a Multi-Layer network.

Links:
    [Cloud  Dataset](https://www.kaggle.com/c/understanding_cloud_organization/data).
Author: Nomi Tzabari, Shai Aharon
Project: https://github.com/aymericdamien/TensorFlow-Examples/
"""

from __future__ import print_function

import argparse
import datetime
import os
from dataclasses import dataclass

import cv2
import numpy as np
import tensorflow as tf

import CNN
from Perceptron import Perceptron
from SimpleAnn import SimpleAnn

USE_GPU = False


@dataclass
class Datapack:
    images: np.ndarray
    labels: np.ndarray
    batch_index = 0

    def next_batch(self, n_batch: int, advance: bool = True) -> (np.ndarray, np.ndarray):
        """
        Gets the next batch of data
        :param n_batch: Size of batch
        :param advance: False if you don't want to advance the index
        :return: A batch of data
        """
        if n_batch < 0:
            self.batch_index = 0
            n_batch = len(self.images)

        if self.batch_index + n_batch >= len(self.images):
            self.batch_index = 0

        mini_batch = (self.images[self.batch_index:self.batch_index + n_batch, :],
                      self.labels[self.batch_index:self.batch_index + n_batch, :])
        if advance:
            self.batch_index = self.batch_index + n_batch
        return mini_batch


def splitData(data: Datapack, ratio: float = 0.7) -> (Datapack, Datapack):
    """
    Splits the data to train/test
    :param data: The data
    :param ratio: The size of train in percentage
    :return: Train, Test
    """
    imgs = data.images
    lbls = data.labels
    n_data = len(lbls)

    idx = [x for x in range(n_data)]
    np.random.shuffle(idx)

    imgs_shuff = imgs[idx, :]
    lbls_shuff = lbls[idx]

    split = int(n_data * ratio)
    train = Datapack(imgs_shuff[:split, :], lbls_shuff[:split])
    test = Datapack(imgs_shuff[split:, :], lbls_shuff[split:])

    return train, test


def preProcess(img):
    """
    Dose some simple pre-process to the images before they go into the NN
    :param img: Original image
    :return: Processed image
    """
    img = cv2.resize(img, (32, 32))
    img = img / 255.0
    # thrs = 0.5
    # img[img < thrs] = 0
    # img[img >= thrs] = 1

    return img


def loadData(folder_path: str, class_cap: int = -1) -> (Datapack, dict):
    """
    Load the data from the data path.
    :param folder_path: Base folder for the data
    :param class_cap: Maximum samples from each category
    :return: The data
    """
    print("Loading data...")
    classes = os.listdir(folder_path)
    class2id = {x: i for i, x in enumerate(classes)}

    images = []
    labels = []
    for clz in classes:
        max_samp = class_cap
        sam_count = 0
        print('\t%s:\t' % clz, end='')
        class_path = os.path.join(folder_path, clz)
        for img_path in os.listdir(class_path):
            img_full_path = os.path.join(class_path, img_path)

            img = cv2.imread(img_full_path, cv2.IMREAD_GRAYSCALE)
            img = preProcess(img)
            img = img.reshape((1, -1))
            images.append(img)
            lbl_vec = np.zeros(len(classes))
            lbl_vec[class2id[clz]] = 1
            labels.append(lbl_vec)
            sam_count += 1
            max_samp -= 1
            if max_samp == 0:
                break

        print(sam_count)

    data = Datapack(
        np.array(images, dtype=np.float32).squeeze(),
        np.array(labels, dtype=np.uint8))
    return data, class2id


def build_and_run(nn, n_input: int, n_classes: int,
                  train: Datapack, test: Datapack,
                  n_steps: int, n_batch: int):
    # Construct model
    # tf Graph input
    X = tf.placeholder("float", [None, n_input])
    Y = tf.placeholder("float", [None, n_classes])
    logits = nn(X)

    # TensorBoard
    # Construct model and encapsulating all ops into scopes, making
    # Tensorboard's Graph visualization more convenient
    with tf.name_scope('Model'):
        # Model
        pred = tf.nn.softmax(logits)
    with tf.name_scope('Loss'):
        # Minimize error using cross entropy

        regularizer = tf.contrib.layers.l1_regularizer(scale=0.000001)
        reg_variables = tf.get_collection(tf.GraphKeys.REGULARIZATION_LOSSES)
        reg_term = tf.contrib.layers.apply_regularization(regularizer, reg_variables)
        loss_op = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits_v2(logits=logits, labels=Y))
        # loss_op += reg_term # Adds the regularization loss
    with tf.name_scope('SGD'):
        # Gradient Descent1
        starter_learning_rate = 0.5
        global_step = tf.Variable(0, trainable=False)
        learning_rate = tf.train.exponential_decay(starter_learning_rate,
                                                   global_step,
                                                   epoch_steps * 40, .5, staircase=True)
        train_op = tf.train.GradientDescentOptimizer(learning_rate).minimize(loss_op, global_step=global_step)
    with tf.name_scope('Accuracy'):
        # Accuracy
        acc = tf.equal(tf.argmax(pred, 1), tf.argmax(Y, 1))
        acc = tf.reduce_mean(tf.cast(acc, tf.float32))

    # Initialize the variables (i.e. assign their default value)
    init = tf.global_variables_initializer()

    # Create a summary to monitor accuracy tensor
    tf.summary.scalar("Accuracy", acc)
    tf.summary.scalar("Loss", loss_op)
    tf.summary.scalar("Learning Rate", learning_rate)
    merged_summary = tf.summary.merge_all()

    # Logging
    tf_logs_path = os.path.join(os.getcwd(), 'tf_logs', args.model , datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
    os.makedirs(os.path.join(tf_logs_path, "train"), exist_ok=True)
    os.makedirs(os.path.join(tf_logs_path, "test"), exist_ok=True)

    # Checkpoints
    checkpoint_path = os.path.join(tf_logs_path, "checkpoints", "model.ckpt")
    os.makedirs(os.path.dirname(checkpoint_path), exist_ok=True)
    saver = tf.train.Saver(max_to_keep=5)

    # Start training
    with tf.Session(config=tf.ConfigProto(allow_soft_placement=True)) as sess:
        # op to write logs to Tensorboard
        summary_writer_train = tf.summary.FileWriter(os.path.join(tf_logs_path, "train"),
                                                     graph=tf.get_default_graph())
        summary_writer_test = tf.summary.FileWriter(os.path.join(tf_logs_path, "test"),
                                                    graph=tf.get_default_graph())

        # Run the initializer
        sess.run(init)

        if args.weights_path:
            # Restore model weights from previously saved model
            saver.restore(sess, args.weights_path)
            print("Model restored from file: %s" % args.weights_path)

        epoch_count = 0
        for step in range(1, n_steps + 1):
            batch_x, batch_y = train.next_batch(n_batch)
            # Run optimization op (backprop)
            c = sess.run(train_op,
                         feed_dict={X: batch_x,
                                    Y: batch_y})

            if step % epoch_steps == 0 or step == 1:
                save_path = saver.save(sess, checkpoint_path, global_step=epoch_count)

                if USE_GPU and not GPU_FULL:
                    train_x, train_y = train.next_batch(n_batch, False)
                    test_x, test_y = test.next_batch(n_batch)
                else:
                    train_x, train_y = train.next_batch(-1)
                    test_x, test_y = test.next_batch(-1)

                train_acc, train_loss, summary_train = sess.run([acc, loss_op, merged_summary],
                                                                feed_dict={X: train_x,
                                                                           Y: train_y})
                summary_writer_train.add_summary(summary_train, step)

                test_acc, test_loss, summary_test = sess.run([acc, loss_op, merged_summary],
                                                             feed_dict={X: test_x,
                                                                        Y: test_y})
                summary_writer_test.add_summary(summary_test, step)
                # Calculate batch loss and accuracy
                print("Epoch " + str(epoch_count)
                      + ",\t Training Accuracy= " + "{:.6f}".format(train_acc)
                      + ",\t Loss= " + "{:.6f}".format(train_loss)
                      + ",\t Test Accuracy= " + "{:.6f}".format(test_acc)
                      + ",\t Loss= " + "{:.6f}".format(test_loss)
                      + ",\t Learning Rate= " + str(learning_rate.eval()))
                epoch_count += 1

        print("Optimization Finished!")

        # Calculate accuracy for the Cloud dataset test images
        print("Testing Accuracy:",
              sess.run(acc, feed_dict={X: test.images,
                                       Y: test.labels}))


def run(args: argparse.Namespace):
    if not USE_GPU:
        os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
    data_folder = os.path.join('data/mini_data')
    data, class2id = loadData(data_folder, args.samples)
    train, test = splitData(data, ratio=0.7)

    # Parameters
    global epoch_steps, epoch
    epoch = len(train.images)
    batch_size = min(epoch, args.mini_batch)
    epoch_steps = (epoch // batch_size)
    num_steps = 1000 * epoch_steps
    print("Steps:", num_steps)

    # Network Parameters
    global num_classes, num_input
    num_input = len(data.images[0])
    num_classes = len(class2id)

    print('Model:', args.model)
    if args.model == 'ANN':
        sim_ann = SimpleAnn(
            hidden_lst=[
                128 ** 2,
                64 ** 2,
                64 ** 2,
                32 ** 2,
                16 ** 2
            ],
            input_num=num_input,
            class_num=num_classes
        )
        net = sim_ann.getModel
    elif args.model == 'SLP':
        perceptron = Perceptron(
            input_num=num_input,
            class_num=num_classes)
        net = perceptron.getModel
    elif args.model == 'CNN':
            CNN.main()
            exit(0)
    else:
        print("Model not valid, use: [SLP,ANN,CNN]")
        exit(1)

    build_and_run(
        net,
        n_input=num_input,
        n_classes=num_classes,
        train=train,
        test=test,
        n_steps=num_steps,
        n_batch=batch_size,
    )


if __name__ == "__main__":
    tf.logging.set_verbosity(tf.logging.INFO)

    parser = argparse.ArgumentParser(description='Train NN')
    parser.add_argument('--model', dest="model", type=str, required=True,
                        help='Which model to use? (SLP,ANN,CNN)')
    parser.add_argument('--batch_size', dest="mini_batch", type=int, default=128,
                        help='Mini Batch size')
    parser.add_argument('--samples', dest="samples", type=int, default=3000,
                        help='How many samples to load from each catagory')
    parser.add_argument('--use_gpu', dest="gpu", type=bool,
                        help='Use GPU?')
    parser.add_argument('--gpu_full', dest="full_gpu", type=bool,
                        help='Test on full test when using GPU?')
    parser.add_argument('--weights', dest="weights_path", type=str,
                        help='Location of weights')

    args = parser.parse_args()
    USE_GPU = args.gpu
    GPU_FULL = args.full_gpu
    args.mini_batch = max(1, args.mini_batch)

    run(args)
