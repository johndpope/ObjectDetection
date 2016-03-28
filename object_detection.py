import network_simple as nn
import tensorflow as tf
import input_data
import utils
import numpy
import cv2
import time
import csv

flags = tf.app.flags
FLAGS = flags.FLAGS

flags.DEFINE_integer('image_size', 28, 'width and height of the input images')
flags.DEFINE_integer('batch_size', 50, 'training batch size')
flags.DEFINE_integer('max_steps', 5000, 'number of steps to run trainer')

flags.DEFINE_string('test_img', '../images/Land.jpg', 'path to test image')

flags.DEFINE_boolean('show_ground_truth', False, 'show ground truth data')
flags.DEFINE_string('test_data', '../space_crater_dataset/data/3_25.csv', 'path to ground truth csv file')

flags.DEFINE_boolean('sliding_window_detection', False, 'enable sliding_window_detection')
flags.DEFINE_integer('step_size', 7, 'sliding window step size')

flags.DEFINE_boolean('candidate_detection', True, 'enable candidate detection')
flags.DEFINE_string('candidate_file','candidates/candidates_land.csv', 'path to candidate file')

flags.DEFINE_string('output_file','output/land_out.png', 'path to output file')

# start session
sess = tf.InteractiveSession()

def import_data():
    """
    Returns a Data object which contains training data
    """
    # Import data
    data = input_data.Data(FLAGS.image_size, FLAGS.image_size)
    #data.add('../images/Land.csv',
    #         '../images/Land.jpg')
    
    data.add('../space_crater_dataset/data/1_24.csv',
             '../space_crater_dataset/images/tile1_24.pgm')
    data.add('../space_crater_dataset/data/1_25.csv',
             '../space_crater_dataset/images/tile1_25.pgm')
    data.add('../space_crater_dataset/data/2_24.csv',
             '../space_crater_dataset/images/tile2_24.pgm')
    data.add('../space_crater_dataset/data/2_25.csv',
             '../space_crater_dataset/images/tile2_25.pgm')
    data.add('../space_crater_dataset/data/3_24.csv',
             '../space_crater_dataset/images/tile3_24.pgm')
    data.add('../space_crater_dataset/data/3_25.csv',
             '../space_crater_dataset/images/tile3_25.pgm')
    data.finalize()
    
    print '(datasets, positive, negative)'
    print data.info()
    print ''
    
    return data


def overall_accuracy(data, x, y_, keep_prob, acc_op):
    """
    returns the accuracy of the model over all data in 'data'
    Args:
        data: data to test
        x: model input placeholder
        y_: desired output placeholder
        keep_prob: keep probability placeholder
        acc_op: accuracy operation
    Returns:
        accuracy of the model (0 < acc < 1)
    """
    global sess
    feed = {x:data.images, y_: data.labels, keep_prob:0.5}
    return sess.run(acc_op, feed_dict = feed)


def train_model(model, data, x, y_, keep_prob):
    """
    trains the model
    Args:
        model: model to train
        data: training datasets
        x: input data placeholder
        y_: desired output placeholder
        keep_prob: keep probability placeholder    
    """
    global sess
    with tf.name_scope('test'):
        correct_prediction = tf.equal(tf.argmax(y_, 1), tf.argmax(model, 1))
        accuracy = tf.reduce_mean(tf.cast(correct_prediction, tf.float32))
        _ = tf.scalar_summary('accuracy', accuracy)
    
    # merge summaries and write them to /tmp/crater_logs
    merged_summary = tf.merge_all_summaries()
    writer = tf.train.SummaryWriter("/tmp/crater_logs", sess.graph_def)
    
    # training
    with tf.name_scope('train'):
        train_step = nn.train(model, y_)
    
    tf.initialize_all_variables().run()
    
    # print overall accuracy
    print 'Overall Accuracy: %s' % (overall_accuracy(data, x, y_, keep_prob, accuracy))
    
    # train the model
    for i in range(FLAGS.max_steps):
        batch_xs, batch_ys = data.next_batch(FLAGS.batch_size)
    
        if i % 100 == 0:
            # record summary data and accuracy
            feed = {x:batch_xs, y_:batch_ys, keep_prob:1.0}
            summary_str, acc = sess.run([merged_summary, accuracy], feed_dict = feed)
            writer.add_summary(summary_str, i)
            print 'Accuracy at step %s: %s' % (i, acc)
        else:
            # train batch
            feed = {x:batch_xs, y_:batch_ys, keep_prob:0.5}
            sess.run(train_step, feed_dict = feed)
            
    # print overall accuracy
    print 'Overall Accuracy: %s' % (overall_accuracy(data, x, y_, keep_prob, accuracy))
    

def sliding_window_detection(model, x, keep_prob, src):
    """
    object detection via sliding windows
    Args:
        model: model which is used for detection
        x: input data placeholder
        keep_prob: keep probability placeholder
        src: image to apply the detection
    Returns:
        list of found craters [(x,y,radius)]
    
    """
    global sess
    objects = []
    for windows, coords in utils.slidingWindow(src, FLAGS.step_size, (FLAGS.image_size, FLAGS.image_size)):
        
        feed = {x:windows, keep_prob:1.0}
        y = sess.run(model, feed_dict = feed)

        for i in range(0, len(y)):
            if y[i][0] < 0.25 and y[i][1] > 0.75:
                objects.append((coords[i][0], coords[i][1], 2))
    return objects       


def csv_to_list(csv_file_path, onlyTrue=False):
    """
    converts the csv file at 'csv_file_path' into a list of integer triples
    Args:
        csv_file_path: path to csv file (3 columns with integer values)
        onlyTrue: returns only rows where the fourth column == 1
    Returns:
        list
    """
    candidates = []
    csv_file = open(csv_file_path, 'rb')
    for row in csv.reader(csv_file, delimiter=','):
        if len(row) < 4 or (not onlyTrue or int(row[3]) == 1):
            candidates.append((int(row[0]), int(row[1]), int(row[2])))
    return candidates


def candidate_detection(model, x, keep_prob, src, candidates):
    """
    object detection via external candidate file
    Args:
        model: model which is used for detection
        x: input data placeholder
        keep_prob: keep probability placeholder
        src: source image
        candidates: list of candidates [(x,y,radius)]
    Returns
        list of found craters [(x,y,radius)]
    """
    x_border = 10
    y_border = 10
    
    # add padding to image
    src = cv2.copyMakeBorder(src, x_border, y_border, x_border, y_border, cv2.BORDER_REPLICATE)
    
    images = []
    for c in candidates:
        x_pos = x_border + c[0]
        y_pos = y_border + c[1]
        diameter = int(c[2] * 2)
        sub_image = utils.getSubImage(src, x_pos, y_pos, (diameter, diameter))
        sub_image = utils.scaleImage(sub_image, (FLAGS.image_size, FLAGS.image_size))
        images.append(sub_image)
        
    images = numpy.array(images).reshape(len(candidates), FLAGS.image_size * FLAGS.image_size)
    feed = {x:images, keep_prob:1.0}
    y = sess.run(model, feed_dict = feed)
    
    objects = []
    for i in range(0, len(y)):
        if y[i][0] < 0.25 and y[i][1] > 0.75:
            objects.append(candidates[i])
    
    return objects
    
def main(_):
    # import data
    data = import_data()

    # ---------- create model ----------------#
    
    # model input placeholder
    x           = tf.placeholder("float", shape=[None, FLAGS.image_size * FLAGS.image_size])
    # desired output placeholder
    y_          = tf.placeholder("float", shape=[None, 2])
    # keep probability placeholder
    keep_prob   = tf.placeholder("float")
    
    # use for 'network_simple' model
    model  = nn.create_network(x, keep_prob, FLAGS.image_size)
    # use for 'network' model
    #model  = nn.create_network(network_input)

    tf.initialize_all_variables().run()

    # ---------- train model -----------------#
    
    start = time.time()
    train_model(model, data, x, y_, keep_prob)
    print 'training time: %d' % (time.time() - start)
    
    # ---------- object detection ------------#
    
    src = utils.getImage(FLAGS.test_img)
    start = time.time()
    
    #sliding window detection
    if FLAGS.sliding_window_detection:
        objects = sliding_window_detection(model, x, keep_prob, src)
    
    # candidate detection
    if FLAGS.candidate_detection:
        candidates = csv_to_list(FLAGS.candidate_file)
        objects = candidate_detection(model, x, keep_prob, src, candidates)
    
    print 'detection time: %d' % (time.time() - start)
    
    # ----------- output ---------------------#
    
    src = cv2.cvtColor(src, cv2.COLOR_GRAY2RGB) * 255
    
    # mark crater candidates
    if FLAGS.candidate_detection:
        for candidate in candidates:
            cv2.circle(src, (candidate[0], candidate[1]), candidate[2], (0,0,255), 0) # red
    
    # mark ground truth craters
    if FLAGS.show_ground_truth:
        ground_truth_data = csv_to_list(FLAGS.test_data, True)
        for crater in ground_truth_data:
            cv2.circle(src, (crater[0], crater[1]), crater[2], (0,255,0), 0) # green
    
    # mark found objects
    for (x,y,r) in objects:
        cv2.circle(src, (x, y), r, (255,0,0), 0) #blue
    
    cv2.imwrite(FLAGS.output_file, src)

if __name__ == '__main__':
    tf.app.run()
