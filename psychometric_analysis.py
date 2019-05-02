import numpy as np
from snep.utils import experiment_opener, filter_tasks
from helper_funcs import plot_psychometric

load_path = '/Users/PSR/Documents/WS19/MasterThesis/Experiments/run_hierarchical'
test_expers = ['2019-04-29-18h06m50s', '2019-04-29-17h40m23s']
plt_show = True
fig_extension = '.png'


@experiment_opener({'test_wimmer':  test_expers[0],
                    'test_naud':  test_expers[1],
                    }, load_path, show=plt_show)
def get_psychometric(tables_task_ids):
    """
    Using the experiment_opener decorator automates some of the tedious aspects of handling experiment
    files, including opening and closing the file, plus it also calls plt.show() if you ask it to.
    And finally, it fixes a problem with SVG files so that they don't explode Inkscape if you import them.

    :param tables_task_ids: dict mapping from user supplied name to a tuple of (tables, task_ids)
    :return:
    """
    from snep.tables.experiment import ExperimentTables

    for t, test in enumerate(tables_task_ids):
        tables, task_ids = tables_task_ids[test]
        assert isinstance(tables, ExperimentTables)  # This allows PyCharm to autocomplete method names for tables
        task_dir = load_path + '/' + str(test)
        fig_name = '/fig_psychometric' + test_expers[t] + fig_extension
        params = tables.get_general_params(True)
        param_ranges = tables.read_param_ranges()

        # params and allocate variables
        c_ranges = param_ranges[('c',)].value
        n_trials = len(param_ranges[('iter',)].value)
        winner_pops = np.empty((len(c_ranges), n_trials))

        for c, c_value in enumerate(c_ranges):    # linspace(-1, 1, 11):
            # filtertasks
            targets = [{('c',): c_value}, ]
            target_ids = filter_tasks(task_ids, targets)

            for i, tid in enumerate(target_ids):
                winner_pops[c, i] = np.logical_not(tables.get_raw_data(tid, 'winner_pop')[0])

        plot_psychometric(c_ranges, winner_pops, task_dir, fig_name)


if __name__ == '__main__':
    get_psychometric()
