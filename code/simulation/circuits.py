# V3.19 by psr
#   - follows code in DB model from Wimmer et al. 2015.
#   - brian2 syntax
#   - uses in cpp_standalone mode
#   - compatible with SNEP
#   - restructured for more readability

import numpy as np
import neuron_models as nm
import get_params as params
from helper_funcs import get_OUstim, unitless, get_this_dt, get_this_time
from brian2 import PoissonGroup, PoissonInput, linked_var, TimedArray, seed, Network
from brian2.groups import NeuronGroup
from brian2.synapses import Synapses
from brian2.units import amp, second


def get_hierarchical_net(task_info):
    """
    Construct hierarchical net for decision making experiment.

    :return: Brian Network object to run and monitors for plotting
    """
    dec_groups, dec_synapses, dec_subgroups = mk_dec_circuit(task_info)
    sen_groups, sen_synapses, sen_subgroups = mk_sen_circuit(task_info)
    fffb_synapses = mk_fffb_synapses(task_info, dec_subgroups, sen_subgroups)

    seed(task_info['seed'])
    # seed(1657831915)
    dec_groups = init_conds_dec(dec_groups)
    sen_groups = init_conds_sen(sen_groups, two_comp=task_info['sim']['2c_model'])
    monitors = mk_monitors(task_info, dec_groups, sen_groups, dec_subgroups, sen_subgroups)
    net = Network(dec_groups.values(), dec_synapses.values(),
                  sen_groups.values(), sen_synapses.values(),
                  fffb_synapses.values(), *monitors, name='hierarchical_net')

    return net, monitors


def get_plasticity_net(task_info):
    """Construct sensory circuit for inhibitory plasticity experiment."""
    sen_groups, sen_synapses, sen_subgroups = mk_sen_circuit_plastic(task_info)

    seed(task_info['seed'])
    sen_groups = init_conds_sen(sen_groups, two_comp=True, plastic=True)
    monitors = mk_monitors_plastic(task_info, sen_groups, sen_subgroups)
    net = Network(sen_groups.values(), sen_synapses.values(), *monitors, name='plasticity_net')

    return net, monitors


def mk_dec_circuit(task_info):
    """
    Creates the 'winner-takes-all' network described in Wang 2002.

    :return: groups, synapses, subgroups
    """
    # load params from task_info
    N_E = task_info['dec']['N_E']       # number of exc neurons (1600)
    N_I = task_info['dec']['N_I']       # number of inh neurons (400)
    sub = task_info['dec']['sub']       # fraction of stim-selective exc neurons
    N_D1 = int(N_E * sub)               # size of exc sub-pop D1, D2
    N_D2 = N_D1                         # size of exc sub-pop D2
    N_D3 = int(N_E * (1 - 2 * sub))     # size of exc sub-pop D3, the rest
    num_method = task_info['sim']['num_method']

    # define namespace
    paramdec = params.get_dec_params(task_info)

    # unpack variables
    d = paramdec['d']
    nu_ext_12 = paramdec['nu_ext_12']
    nu_ext_3I = paramdec['nu_ext_3I']

    # neuron groups
    decE = NeuronGroup(N_E, model=nm.eqs_wang_exc, method=num_method, threshold='V>=Vt', reset='V=Vr',
                       refractory='tau_refE', namespace=paramdec, name='decE')
    decE1 = decE[:N_D1]
    decE2 = decE[N_D1:N_D1 + N_D2]
    decE3 = decE[-N_D3:]
    decE1.label = 1
    decE2.label = 2
    decE3.label = 3

    decI = NeuronGroup(N_I, model=nm.eqs_wang_inh, method=num_method, threshold='V>=Vt', reset='V=Vr',
                       refractory='tau_refI', namespace=paramdec, name='decI')

    # weight connections according to different subgroups
    condsame = '(label_pre != 3 and label_pre == label_post)'
    conddiff = '(label_pre != 3 and label_pre != label_post) or (label_pre == 3 and label_post != 3)'
    condrest = '(label_post == 3)'

    # NMDA: exc --> exc
    synDEDEn = Synapses(decE, decE, model=nm.eqs_NMDA, method=num_method,
                        on_pre='x_en += w', delay=d,
                        namespace=paramdec, name='synDEDEn')
    synDEDEn.connect()
    synDEDEn.w['i == j'] = 1
    synDEDEn.w['i != j'] = 0
    synDEDEn.w_nmda[condsame] = 'w_p * gEEn/gleakE'
    synDEDEn.w_nmda[conddiff] = 'w_m * gEEn/gleakE'
    synDEDEn.w_nmda[condrest] = 'gEEn/gleakE'

    # NMDA: exc --> inh
    decI.w_nmda = '(gEIn/gleakI) / (gEEn/gleakE)'
    decI.g_ent = linked_var(decE3, 'g_ent', index=range(N_I))

    # AMPA: exc --> exc
    synDEDEa = Synapses(decE, decE, model='w : 1', method=num_method,
                        on_pre='g_ea += w', delay=d,
                        namespace=paramdec, name='synDEDEa')
    synDEDEa.connect()
    synDEDEa.w[condsame] = 'w_p * gEEa/gleakE'
    synDEDEa.w[conddiff] = 'w_m * gEEa/gleakE'
    synDEDEa.w[condrest] = 'gEEa/gleakE'

    # AMPA: exc --> inh
    synDEDIa = Synapses(decE, decI, model='w : 1', method=num_method,
                        on_pre='g_ea += w', delay=d,
                        namespace=paramdec, name='synDEDIa')
    synDEDIa.connect()
    synDEDIa.w = 'gEIa/gleakI'

    # GABA: inh --> exc
    synDIDE = Synapses(decI, decE, model='w : 1', method=num_method,
                       on_pre='g_i += w', delay=d,
                       namespace=paramdec, name='synDIDE')
    synDIDE.connect()
    synDIDE.w = 'gIE/gleakE'

    # GABA: inh --> inh
    synDIDI = Synapses(decI, decI, model='w : 1', method=num_method,
                       on_pre='g_i += w', delay=d,
                       namespace=paramdec, name='synDIDI')
    synDIDI.connect()
    synDIDI.w = 'gII/gleakI'

    # external inputs
    extE = PoissonInput(decE[:N_D1+N_D2], 'g_ea', N=1, rate=nu_ext_12, weight='gXE/gleakE')
    extE3 = PoissonInput(decE3, 'g_ea', N=1, rate=nu_ext_3I, weight='gXE/gleakE')
    extI = PoissonInput(decI, 'g_ea', N=1, rate=nu_ext_3I, weight='gXI/gleakI')

    # variables to return
    groups = {'DE': decE, 'DI': decI, 'DX': extE, 'DX3': extE3, 'DXI': extI}
    subgroups = {'DE1': decE1, 'DE2': decE2, 'DE3': decE3}
    synapses = {'synDEDEn': synDEDEn, 'synDEDEa': synDEDEa, 'synDEDIa': synDEDIa,
                'synDIDE': synDIDE, 'synDIDI': synDIDI}

    return groups, synapses, subgroups


def mk_sen_circuit(task_info):
    """
    Creates balance network representing sensory circuit.

    :return: groups, synapses, subgroups
    """
    # load params from task_info
    N_E = task_info['sen']['N_E']       # number of exc neurons (1600)
    N_I = task_info['sen']['N_I']       # number of inh neurons (400)
    N_X = task_info['sen']['N_X']       # size of external population
    sub = task_info['sen']['sub']       # fraction of stim-selective exc neurons
    N_E1 = int(N_E * sub)               # size of exc sub-pop 1, 2
    num_method = task_info['sim']['num_method']
    two_comp = task_info['sim']['2c_model']

    # define namespace
    if two_comp:
        paramsen = params.get_2c_params(task_info)
    else:
        paramsen = params.get_sen_params(task_info)

    # neuron groups
    if two_comp:
        eqs_soma = nm.eqs_naud_soma + nm.eqs_stim_array
        senE = NeuronGroup(N_E, model=eqs_soma, method=num_method, threshold='V>=Vt',
                           reset='''V = Vl
                                    w_s += bws''',
                           refractory='tau_refE', namespace=paramsen, name='senE')
        dend = NeuronGroup(N_E, model=nm.eqs_naud_dend, method=num_method, namespace=paramsen, name='dend')
        senE.V_d = linked_var(dend, 'V_d')
        dend.lastspike_soma = linked_var(senE, 'lastspike')
        senE1 = senE[:N_E1]
        senE2 = senE[N_E1:]
        dend1 = dend[:N_E1]
        dend2 = dend[N_E1:]
    else:
        senE = NeuronGroup(N_E, model=nm.eqs_wimmer_exc, method=num_method, threshold='V>=Vt', reset='V=Vr',
                           refractory='tau_refE', namespace=paramsen, name='senE')
        senE1 = senE[:N_E1]
        senE2 = senE[N_E1:]

    senI = NeuronGroup(N_I, model=nm.eqs_wimmer_inh, method=num_method, threshold='V>=Vt', reset='V=Vr',
                       refractory='tau_refI', namespace=paramsen, name='senI')

    # external population
    extS = PoissonGroup(N_X, rates='nu_ext', namespace=paramsen)

    # synapses
    synapses = mk_sen_synapses(task_info, senE, senI, extS, paramsen)

    # variables to return
    if two_comp:
        groups = {'SE': senE, 'dend': dend, 'SI': senI, 'SX': extS}
        subgroups = {'SE1': senE1, 'SE2': senE2, 'dend1': dend1, 'dend2': dend2}
    else:
        groups = {'SE': senE, 'SI': senI, 'SX': extS}
        subgroups = {'SE1': senE1, 'SE2': senE2}

    return groups, synapses, subgroups


def mk_sen_circuit_plastic(task_info):
    """
    Creates sensory circuit with inhibitory plasticity acting on dendrites.

    :return: groups, synapses, subgroups
    """
    # load params from task_info
    N_E = task_info['sen']['N_E']       # number of exc neurons (1600)
    N_I = task_info['sen']['N_I']       # number of inh neurons (400)
    N_X = task_info['sen']['N_X']       # size of external population
    sub = task_info['sen']['sub']       # fraction of stim-selective exc neurons
    N_E1 = int(N_E * sub)               # size of exc sub-pop 1, 2
    num_method = task_info['sim']['num_method']

    # define namespace
    paramplastic = params.get_plasticity_params(task_info)
    tau_update = paramplastic['tau_update']

    # equations
    if task_info['sim']['online_stim']:
        eqs_soma_plastic = nm.eqs_naud_soma + nm.eqs_stim_linked
        paramstim = params.get_stim_params(task_info)
        paramplastic = {**paramplastic, **paramstim}
    else:
        eqs_soma_plastic = nm.eqs_naud_soma + nm.eqs_stim_array

    # neuron groups
    eqs_dend_plastic = nm.eqs_naud_dend + nm.eqs_plasticity
    senE = NeuronGroup(N_E, model=eqs_soma_plastic, method=num_method, threshold='V>=Vt',
                       reset='''V = Vl
                                w_s += bws''',
                       refractory='tau_refE', namespace=paramplastic, name='senE')
    dend = NeuronGroup(N_E, model=eqs_dend_plastic, method=num_method, threshold='burst_start > 1 + min_burst_stop',
                       reset='''B += 1
                                burst_start = 0''',
                       refractory='burst_stop >= min_burst_stop', namespace=paramplastic, name='dend')
    senI = NeuronGroup(N_I, model=nm.eqs_wimmer_inh, method=num_method, threshold='V>=Vt', reset='V=Vr',
                       refractory='tau_refI', namespace=paramplastic, name='senI')
    extS = PoissonGroup(N_X, rates='nu_ext', namespace=paramplastic)

    # subgroups
    senE1 = senE[:N_E1]
    senE2 = senE[N_E1:]
    dend1 = dend[:N_E1]
    dend2 = dend[N_E1:]

    # linked variables
    senE.V_d = linked_var(dend, 'V_d')
    dend.lastspike_soma = linked_var(senE, 'lastspike')

    # soma-dendrite synapse
    syn_burst_trace = Synapses(senE, dend, method=num_method, on_pre='''burst_start +=1
                                                                        burst_stop = 1''',
                               namespace=paramplastic, name='syn_burst_trace')
    syn_burst_trace.connect(j='i')

    # stim
    if task_info['sim']['online_stim']:
        stim_dt = paramstim['stim_dt']
        stim_common = NeuronGroup(2, model=nm.eqs_stim_common, method=num_method,
                                  dt=stim_dt, namespace=paramstim, name='stim_common')
        stimE = NeuronGroup(N_E, model=nm.eqs_stim_online, method=num_method,
                            dt=stim_dt, namespace=paramstim, name='stimE')
        stimE1 = stimE[:N_E1]
        stimE2 = stimE[N_E1:]
        stimE.z = linked_var(stim_common, 'z', index=np.hstack((np.zeros(N_E1, dtype=int), np.ones(N_E1, dtype=int))))
        stimE1.mu = paramstim['mu1']
        stimE2.mu = paramstim['mu2']
        senE.I = linked_var(stimE, 'I')

    # update rule
    dend1.muOUd = 0*amp     #'-95*pA - rand()*10*pA'  # random initialisation in [-105:-95 pA], 0*amp
    dend1.run_regularly('muOUd = clip(muOUd - eta * (B - B0), -100*amp, 0)', dt=tau_update)

    # connections
    sen_synapses = mk_sen_synapses(task_info, senE, senI, extS, paramplastic)
    extD1, synDXdend1 = mk_poisson_fb(task_info, dend1)

    # variables to return
    groups = {'SE': senE, 'dend': dend, 'SI': senI, 'SX': extS, 'DX': extD1}
    subgroups = {'SE1': senE1, 'SE2': senE2,
                 'dend1': dend1, 'dend2': dend2}
    synapses = {**sen_synapses, **{'synDXdend': synDXdend1, 'syn_burst_trace': syn_burst_trace}}

    if task_info['sim']['online_stim']:
        groups = {**groups, **{'stim_common': stim_common, 'stimE': stimE}}

    return groups, synapses, subgroups


def mk_sen_synapses(task_info, exc, inh, ext, param_space):
    """creates synapses for the different types of sensory circuits"""
    # unpack variables
    num_method = task_info['sim']['num_method']
    sub = task_info['sen']['sub']
    dE = param_space['dE']
    dI = param_space['dI']
    dX = param_space['dX']

    # weight according to different subgroups
    condsame = '(i<N_pre*sub and j<N_post*sub) or (i>=N_pre*sub and j>=N_post*sub)'
    conddiff = '(i<N_pre*sub and j>=N_post*sub) or (i>=N_pre*sub and j<N_post*sub)'

    # AMPA: exc --> exc
    synSESE = Synapses(exc, exc, model='w : 1', method=num_method,
                       on_pre='''x_ea += w
                                 w = clip(w, 0, gmax)''',
                       namespace=param_space, name='synSESE')
    synSESE.connect(p='eps')
    synSESE.w[condsame] = 'w_p * gEE/gleakE * (1 + randn()*0.5)'
    synSESE.w[conddiff] = 'w_m * gEE/gleakE * (1 + randn()*0.5)'
    synSESE.delay = dE

    # AMPA: exc --> inh
    synSESI = Synapses(exc, inh, model='w : 1', method=num_method,
                       on_pre='''x_ea += w
                                 w = clip(w, 0, gmax)''',
                       namespace=param_space, name='synSESI')
    synSESI.connect(p='eps')
    synSESI.w = 'gEI/gleakI * (1 + randn()*0.5)'
    synSESI.delay = dE

    # GABA: inh --> exc
    synSISE = Synapses(inh, exc, model='w : 1', method=num_method,
                       on_pre='''x_i += w
                                 w = clip(w, 0, gmax)''',
                       namespace=param_space, name='synSISE')
    synSISE.connect(p='eps')
    synSISE.w = 'gIE/gleakE * (1 + randn()*0.5)'
    synSISE.delay = dI

    # GABA: inh --> inh
    synSISI = Synapses(inh, inh, model='w : 1', method=num_method,
                       on_pre='''x_i += w
                                 w = clip(w, 0, gmax)''',
                       namespace=param_space, name='synSISI')
    synSISI.connect(p='eps')
    synSISI.w = 'gII/gleakI * (1 + randn()*0.5)'
    synSISI.delay = dI

    # external inputs and synapses
    synSXSE = Synapses(ext, exc, model='w : 1', method=num_method,
                       on_pre='''x_ea += w
                                 w = clip(w, 0, gmax)''',
                       namespace=param_space, name='synSXSE')
    synSXSE.connect(condition=condsame, p='epsX * (1 + alphaX)')
    synSXSE.connect(condition=conddiff, p='epsX * (1 - alphaX)')
    synSXSE.w = 'gXE/gleakE * (1 + randn()*0.5)'
    synSXSE.delay = dX

    synSXSI = Synapses(ext, inh, model='w : 1', method=num_method,
                       on_pre='''x_ea += w
                                 w = clip(w, 0, gmax)''',
                       namespace=param_space, name='synSXSI')
    synSXSI.connect(p='epsX')
    synSXSI.w = 'gXI/gleakI * (1 + randn()*0.5)'
    synSXSI.delay = dX

    # variables to return
    synapses = {'synSESE': synSESE, 'synSESI': synSESI,
                'synSISE': synSISE, 'synSISI': synSISI,
                'synSXSE': synSXSE, 'synSXSI': synSXSI}

    return synapses


def mk_sen_stimulus(task_info, arrays=False):
    """
    Generate common and private part of the stimuli for sensory neurons from an OU process.

    :return: TimedArray with the stimulus for sensory excitatory neurons
    """
    # set seed with np - for standalone mode brian's seed() is not sufficient!
    if task_info['sim']['replicate_stim']:
        # replicated stimuli across iters
        np.random.seed(123)
    else:
        # every iter has different stimuli
        np.random.seed(task_info['seed'])

    # TimedArray stim
    if not task_info['sim']['online_stim']:
        # simulation params
        nn = int(task_info['sen']['N_E'] * task_info['sen']['sub'])     # no. of neurons in sub-pop1
        stim_dt = task_info['sim']['stim_dt']
        runtime = unitless(task_info['sim']['runtime'], stim_dt)
        stim_on = unitless(task_info['sim']['stim_on'], stim_dt)
        stim_off = unitless(task_info['sim']['stim_off'], stim_dt)
        flip_stim = task_info['sim']['ramp_stim']
        stim_time = get_this_time(task_info, runtime, include_settle_time=True)
        tps = stim_off - stim_on                             # total stim points

        # stimulus namespace
        paramstim = params.get_stim_params(task_info)
        tau = unitless(paramstim['tau_stim'], stim_dt)      # OU time constant
        c = paramstim['c']
        I0 = paramstim['I0']
        I0_wimmer = paramstim['I0_wimmer']
        mu1 = paramstim['mu1']
        mu2 = paramstim['mu2']
        if task_info['sim']['ramp_stim']:
            # smooth the stim onset with a positive exponential decay
            tau_ramp = 20e-3 / unitless(stim_dt, second, as_int=False)
            mu1 *= (1 - np.exp(-np.arange(tps) / tau_ramp))
            mu2 *= (1 - np.exp(-np.arange(tps) / tau_ramp))
            mu1 = mu1[None, :]
            mu2 = mu2[None, :]
        sigma_stim = paramstim['sigma_stim']
        sigma_ind = paramstim['sigma_ind']

        # common and private part
        z1 = np.tile(get_OUstim(tps, tau, flip_stim), (nn, 1))
        z2 = np.tile(get_OUstim(tps, tau, flip_stim), (nn, 1))
        np.random.seed(np.random.randint(10000))
        zk1 = get_OUstim(tps * nn, tau, flip_stim).reshape(nn, tps)
        zk2 = get_OUstim(tps * nn, tau, flip_stim).reshape(nn, tps)

        # stim2TimedArray with zero padding if necessary
        i1 = I0 + I0_wimmer * (c * mu1 + sigma_stim * z1 + sigma_ind * zk1)
        i2 = I0 + I0_wimmer * (c * mu2 + sigma_stim * z2 + sigma_ind * zk2)
        stim1 = i1.T.astype(np.float32)
        stim2 = i2.T.astype(np.float32)
        i1t = np.concatenate((np.zeros((stim_on, nn)), stim1,
                              np.zeros((runtime - stim_off, nn))), axis=0).astype(np.float32)
        i2t = np.concatenate((np.zeros((stim_on, nn)), stim2,
                              np.zeros((runtime - stim_off, nn))), axis=0).astype(np.float32)
        Irec = TimedArray(np.concatenate((i1t, i2t), axis=1)*amp, dt=stim_dt)

        if arrays:
            stim1 = i1t.T.astype(np.float32)
            stim2 = i2t.T.astype(np.float32)
            stim_fluc = np.hstack((np.zeros(stim_on), z1[0] - z2[0], np.zeros(runtime-stim_off)))
            return Irec, stim1, stim2, stim_time, stim_fluc

        return Irec


def mk_fffb_synapses(task_info, dec_subgroups, sen_subgroups):
    """
    Feedforward and feedback synapses of hierarchical network.

    :return: dictionary with the synapses objects
    """
    # params
    paramfffb = params.get_fffb_params(task_info)
    d = paramfffb['d']
    num_method = task_info['sim']['num_method']
    two_comp = task_info['sim']['2c_model']

    # unpack subgroups
    decE1 = dec_subgroups['DE1']
    decE2 = dec_subgroups['DE2']
    senE1 = sen_subgroups['SE1']
    senE2 = sen_subgroups['SE2']
    if not two_comp:
        fb_target1 = senE1
        fb_target2 = senE2
    else:
        fb_target1 = sen_subgroups['dend1']
        fb_target2 = sen_subgroups['dend2']

    # create FF and FB synapses
    synSE1DE1 = Synapses(senE1, decE1, model='w = w_ff : 1', method=num_method,
                         on_pre='g_ea += w', delay=d, name='synSE1DE1', namespace=paramfffb)
    synSE2DE2 = Synapses(senE2, decE2, model='w = w_ff : 1', method=num_method,
                         on_pre='g_ea += w', delay=d, name='synSE2DE2', namespace=paramfffb)
    synDE1SE1 = Synapses(decE1, fb_target1, model='w = w_fb : 1', method=num_method,
                         on_pre='x_ea += w', delay=d, name='synDE1SE1', namespace=paramfffb)
    synDE2SE2 = Synapses(decE2, fb_target2, model='w = w_fb : 1', method=num_method,
                         on_pre='x_ea += w', delay=d, name='synDE2SE2', namespace=paramfffb)
    for syn in [synSE1DE1, synSE2DE2, synDE1SE1, synDE2SE2]:
        syn.connect(p='eps')

    fffb_synapses = {'synSE1DE1': synSE1DE1, 'synSE2DE2': synSE2DE2,
                     'synDE1SE1': synDE1SE1, 'synDE2SE2': synDE2SE2}

    return fffb_synapses


def mk_poisson_fb(task_info, dend1):
    """
    Feedback synapses from poisson mimicking decision circuit, to sensory plastic subpopulation.

    :return: a poisson group and a synapse object
    """
    # params
    paramfffb = params.get_fffb_params(task_info)
    d = paramfffb['d']
    num_method = task_info['sim']['num_method']

    # Poisson group
    N_E = task_info['dec']['N_E']           # number of exc neurons (1600)
    subDE = task_info['dec']['sub']         # stim-selective fraction in decision exc neurons
    N_DX = int(subDE * N_E)                 # number decision mock neurons
    extD1 = PoissonGroup(N_DX, rates=task_info['plastic']['dec_winner_rate'])

    # FB synapse
    synDXdend1 = Synapses(extD1, dend1, model='w = w_fb : 1', method=num_method,
                          on_pre='x_ea += w', delay=d, name='synDXdend1', namespace=paramfffb)
    synDXdend1.connect(p='eps')

    return extD1, synDXdend1


def init_conds_dec(dec_groups):
    dec_groups['DE'].V = '-50*mV + 2*mV * rand()'
    dec_groups['DI'].V = '-50*mV + 2*mV * rand()'

    return dec_groups


def init_conds_sen(sen_groups, two_comp=False, plastic=False):
    if two_comp:
        # sen_groups['SE'].V = '-70*mV + 2*mV * rand()'
        # sen_groups['SI'].V = '-70*mV + 2*mV * rand()'
        sen_groups['SE'].V = '-52*mV + 2*mV*rand()'
        sen_groups['SI'].V = '-52*mV + 2*mV*rand()'
        sen_groups['SE'].g_ea = '0.05 * (1 + 0.2*rand())'
        sen_groups['SI'].g_ea = '0.05 * (1 + 0.2*rand())'
        if not plastic:
            pass
            # last_muOUd = np.loadtxt('last_muOUd.csv')
            # sen_groups['dend'].muOUd = np.tile(last_muOUd, 2) * amp
    else:
        sen_groups['SE'].V = '-52*mV + 2*mV*rand()'
        sen_groups['SI'].V = '-52*mV + 2*mV*rand()'
        sen_groups['SE'].g_ea = '0.05 * (1 + 0.2*rand())'
        sen_groups['SI'].g_ea = '0.05 * (1 + 0.2*rand())'

    return sen_groups


def mk_monitors(task_info, dec_groups, sen_groups, dec_subgroups, sen_subgroups):
    """Define monitors to track results from hierarchical experiment."""
    from brian2.monitors import SpikeMonitor, PopulationRateMonitor

    # unpack neuron groups
    senE = sen_groups['SE']
    decE1 = dec_subgroups['DE1']
    decE2 = dec_subgroups['DE2']
    senE1 = sen_subgroups['SE1']
    senE2 = sen_subgroups['SE2']

    # create monitors
    spksSE = SpikeMonitor(senE)
    rateDE1 = PopulationRateMonitor(decE1)
    rateDE2 = PopulationRateMonitor(decE2)
    rateSE1 = PopulationRateMonitor(senE1)
    rateSE2 = PopulationRateMonitor(senE2)

    monitors = [spksSE, rateDE1, rateDE2, rateSE1, rateSE2]

    if task_info['sim']['plt_fig1']:
        decE = dec_groups['DE']
        nnDE = int(task_info['dec']['N_E'] * 2 * task_info['dec']['sub'])
        spksDE = SpikeMonitor(decE[:nnDE])
        rateDI = PopulationRateMonitor(dec_groups['DI'])
        rateSI = PopulationRateMonitor(sen_groups['SI'])
        monitors = monitors + [spksDE, rateDI, rateSI]

    return monitors


def mk_monitors_plastic(task_info, sen_groups, sen_subgroups):
    """Define monitors to track results from plasticity experiment."""
    from brian2.monitors import SpikeMonitor, StateMonitor, PopulationRateMonitor

    # unpack neuron groups
    senE = sen_groups['SE']
    dend1 = sen_subgroups['dend1']

    # create monitors
    stim_dt = task_info['sim']['stim_dt']
    spksSE = SpikeMonitor(senE)
    dend_mon = StateMonitor(dend1, variables=['muOUd', 'Ibg', 'g_ea', 'B'], record=True, dt=stim_dt)
    spks_dend = SpikeMonitor(dend1)
    pop_dend = PopulationRateMonitor(dend1)
    online_stim_mon = StateMonitor(senE, variables=['I'], record=True, dt=stim_dt)

    return [spksSE, dend_mon, online_stim_mon, spks_dend, pop_dend]
