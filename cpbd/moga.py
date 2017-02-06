from deap import base
from deap import creator
from deap import tools

import random
import pickle
import numpy as np

try:
    from mpi4py import MPI
    
    MPI_COMM = MPI.COMM_WORLD
    MPI_SIZE = MPI_COMM.Get_size()
    MPI_RANK = MPI_COMM.Get_rank()
    
except Exception:
    MPI_SIZE = 1
    MPI_RANK = 0


class Moga():
    """
    docstring for Moga
    """
    
    def __init__(self, bounds, weights=(-1.0,)):
        
        # population and elite population sizes
        self.pop_num = 100
        self.elite_num = int(self.pop_num / 10)

        # cross and mutation probability
        self.cxpb, self.mutpb = 0.95, 0.95

        # number of generation
        self.ngen = 10

        # infinite value
        self.inf_val = float("inf")

        self.weights = weights
        self.problem_size = len(self.weights)

        self.penalty = None

        self.log_print = True if MPI_RANK == 0 else False
        self.log_file = 'moga_result.dat' if MPI_RANK == 0 else None
        self.plt_file = 'moga_plot.dat' if MPI_RANK == 0 else None

        self.fit_func = lambda x: None
        self.fit_func_args = []

        self.vars_num = len(bounds)
        self.bounds_min = []
        self.bounds_max = []
        for i in range(len(bounds)):
            self.bounds_min.append(bounds[i][0])
            self.bounds_max.append(bounds[i][1])
        

    def set_params(self, pop_num=None, weights=None, elite=None, penalty=None, cxpb=None, mutpb=None, ngen=None, log_print=None, log_file=None, plt_file=None):
        
        if pop_num != None:
            self.pop_num = pop_num
            self.elite_num = int(self.pop_num / 10)

        if weights != None:
            self.weights = weights
            self.problem_size = len(self.weights)

        if elite != None and elite < self.pop_num:
            self.elite = elite

        if penalty != None:
            self.penalty = penalty

        if cxpb != None:
            self.cxpb = cxpb

        if mutpb != None:
            self.mutpb = mutpb

        if ngen != None:
            self.ngen = ngen

        if log_print != None and MPI_RANK == 0:
            self.log_print = True

        if log_file != None and MPI_RANK == 0:
            self.log_file = log_file

        if plt_file != None and MPI_RANK == 0:
            self.plt_file = plt_file


    def generate_ind(self):
        return [random.uniform(self.bounds_min[i], self.bounds_max[i]) for i in range(self.vars_num)]


    def init_deap_functions(self):

        creator.create("Fitness", base.Fitness, weights=self.weights)
        creator.create("Individual", list, fitness=creator.Fitness)

        toolbox = base.Toolbox()

        toolbox.register("individual", tools.initIterate, creator.Individual, self.generate_ind)
        toolbox.register("population", tools.initRepeat, list, toolbox.individual)

        toolbox.register("evaluate", self.fit_func)

        if self.penalty != None:
            toolbox.decorate("evaluate", tools.DeltaPenality(self.feasible, self.inf_val))

        # crossover - mate
        #toolbox.register("mate", tools.cxTwoPoint)
        toolbox.register("mate", tools.cxSimulatedBinaryBounded, low=self.bounds_min, up=self.bounds_max, eta=10.0) 

        #toolbox.register("mutate", tools.mutGaussian, mu=0.0, sigma=0.2, indpb=MUTPB)
        toolbox.register("mutate", tools.mutPolynomialBounded, eta=10.0, low=self.bounds_min, up=self.bounds_max, indpb=self.mutpb)

        return toolbox


    def feasible(self):
        return True


    def optimize(self, toolbox, init_pop):

        # Create initial population
        pop = self.init_pop(toolbox, init_pop)

        if self.log_print: print("-- Generation 0 --")
        if self.log_file: 
            fh1 = open(self.log_file, 'w')
            fh1.close()
        
        # Evaluate initial population
        pop = self.eval_pop(toolbox, pop)


        # Begin the evolution
        for g in range(self.ngen):

            if self.log_print: print("-- Generation %i --" % (g+1))

            if self.log_file: 
                fh1 = open(self.log_file, 'a')
                fh1.write("\n-------------------------- Generation %i from %i --------------------------\n" % ((g+1), self.ngen))
                fh1.close()

            # Select good and bad individuals
            good_inds = self.get_good_inds(toolbox, pop)

            # Create elite population (non dominated individuals)
            nond_inds = self.get_nondominated_inds(toolbox, pop)

            if self.log_file: 
                fh1 = open(self.log_file, 'a')
                fh1.write("\nNon dominated individuals\n")
                for ind in nond_inds:
                   fh1.write("ind --> fit_func: " + str(ind) + ' --> ' + str(ind.fitness.values) + '\n')
                fh1.close()

            # Save current population to file
            if self.plt_file != None:
                
                data_file = []
                data_file.append([g+1,self.ngen])
                
                val_g = []
                for ind in good_inds:
                    val_g.append(ind.fitness.values)
                data_file.append(val_g)

                val_nd = []
                for ind in nond_inds:
                    val_nd.append(ind.fitness.values)
                data_file.append(val_nd)
                
                with open(self.plt_file, 'wb') as fh2:
                    pickle.dump(data_file, fh2, protocol=2)

            # Select individuals with best solution (best_inds[0] - with best fit_func_1 and best_inds[1] - with best fit_func_2)
            best_inds = self.get_best_inds(toolbox, pop)

            if self.log_file: 
                fh1 = open(self.log_file, 'a')
                fh1.write("\nBest individuals\n")
                for ind in best_inds:
                    fh1.write("ind --> fit_func: " + str(ind) + ' --> ' + str(ind.fitness.values) + '\n')
                fh1.close()

            # Select the next generation individuals
            offspring = self.apply_select(toolbox, pop)

            # Apply crossover on the offspring
            offspring = self.apply_crossover(toolbox, offspring)

            # Apply mutation on the offspring
            offspring = self.apply_mutation(toolbox, offspring)

            # Select and evaluate individuals with invalid fitness
            if MPI_RANK == 0:
                invalid_ind = [ind for ind in offspring if not ind.fitness.valid]
            else:
                invalid_ind = None
            
            invalid_ind = self.eval_pop(toolbox, invalid_ind)

            # The population is entirely replaced by the offspring
            if MPI_RANK == 0: pop = offspring

            # Replace random individuals by elite
            pop = self.replace_rand_inds(toolbox, pop, nond_inds, self.elite_num)

            # Replace individuals with invalid (INF) fitness by new random
            pop = self.replace_bad_inds(toolbox, pop)

            # Select and evaluate individuals with invalid fitness
            if MPI_RANK == 0:
                invalid_ind = [ind for ind in pop if not ind.fitness.valid]
            else:
                invalid_ind = None

            invalid_ind = self.eval_pop(toolbox, invalid_ind)

            # Replace individuals with invalid (INF) fitness by good
            pop = self.replace_bad_inds(toolbox, pop, good_inds)

            # Replace random individuals by bests
            pop = self.replace_rand_inds(toolbox, pop, best_inds)

        return pop


    def init_pop(self, toolbox, init_pop):

        if MPI_RANK != 0: return None

        pop = toolbox.population(n=self.pop_num)
        if init_pop != None:            
            
            init_pop_len = len(init_pop) if len(init_pop) <= self.pop_num else self.pop_num

            for i in range(init_pop_len):
                for j in range(len(init_pop[i])):
                    pop[i][j] = init_pop[i][j]

        return pop

    
    def eval_pop(self, toolbox, pop):

        # Split data
        if MPI_SIZE > 1:
            data_in = None
            if MPI_RANK == 0:
                data_in = []
                length = int(len(pop) / MPI_SIZE)
                for i in range(MPI_SIZE):
                    start = i * length
                    stop = start + length
                    data_in.append(pop[start:stop])
                    
                j = 0
                for i in range(stop, len(pop)):
                    data_in[j] += [pop[i]]
                    j += 1
        
            data_in = MPI_COMM.scatter(data_in, root=0)
        else:
            data_in = pop
        
        # Evaluate initial population
        fitnesses = [toolbox.evaluate(x0=x, args=self.fit_func_args) for x in data_in]

        
        # Merge data
        if MPI_SIZE > 1:
            data_out = MPI_COMM.gather(fitnesses, root=0)
        
            if MPI_RANK == 0:
                fitnesses = []
                for i in data_out:
                    fitnesses += i[:length]
                for i in data_out:
                    fitnesses += i[length:length+1]
                    j -= 1
                    if j == 0: break

        # Update population data
        if MPI_RANK == 0:
            for ind, fit in zip(pop, fitnesses):
                ind.fitness.values = fit
        else:
            pop = None

        if self.log_print: print("Evaluated %i" % (len(pop)))

        return pop


    def get_good_inds(self, toolbox, pop):

        if MPI_RANK != 0: return None

        g_inds = []
        gb = [0, 0]

        for i in pop:
            inf_val_checker = 1
            for j in range(self.problem_size):
                if i.fitness.values[j] == self.inf_val:
                    inf_val_checker *= 0
                
            if inf_val_checker == 1:
                g_inds.append(toolbox.clone(i))
                gb[0] += 1
            else:
                gb[1] += 1

#        for i in pop:
#            if i.fitness.values[0] != self.inf_val and i.fitness.values[1] != self.inf_val:
#                g_inds.append(toolbox.clone(i))
#                gb[0] += 1
#            else:
#                gb[1] += 1
                
        if self.log_print: print("good/bad solitions %i / %i" % (gb[0], gb[1]))

        return g_inds


    def get_nondominated_inds(self, toolbox, pop):

        if MPI_RANK != 0: return None

        nd_inds = tools.sortNondominated(pop, k=len(pop), first_front_only=True)[0]
        nd_inds = [toolbox.clone(x) for x in nd_inds]

        if self.log_print: print("non dominated %i" % len(nd_inds))

        return nd_inds


    def get_best_inds(self, toolbox, pop):
        # only for minimization problem
        
        if MPI_RANK != 0: return None

        best_ind = []
        for j in range(self.problem_size):
            best_ind.append(pop[0])
          
        for ind in pop:
            for j in range(self.problem_size):
                if ind.fitness.values[j] < best_ind[j].fitness.values[j]:
                    best_ind[j] = ind

        #best_ind = [pop[0], pop[0]]
        #for ind in pop:
        #    if ind.fitness.values[0] < best_ind[0].fitness.values[0]:
        #        best_ind[0] = ind
        #    if ind.fitness.values[1] < best_ind[1].fitness.values[1]:
        #        best_ind[1] = ind

        return toolbox.clone(best_ind)


    def apply_select(self, toolbox, pop):

        if MPI_RANK != 0: return None

        offspring = toolbox.select(pop, len(pop))
        offspring = [toolbox.clone(x) for x in offspring]

        return offspring


    def apply_crossover(self, toolbox, pop):

        if MPI_RANK != 0: return None

        for child1, child2 in zip(pop[::2], pop[1::2]):
                
            # cross two individuals with probability CXPB
            if random.random() < self.cxpb:
                toolbox.mate(child1, child2)
                    
                # fitness values of the children
                # must be recalculated later
                del child1.fitness.values
                del child2.fitness.values

        return pop


    def apply_mutation(self, toolbox, pop):
        
        if MPI_RANK != 0: return None

        for mutant in pop:

            # mutate an individual with probability MUTPB
            if random.random() < self.mutpb:
                toolbox.mutate(mutant)
                del mutant.fitness.values

        return pop


    def replace_rand_inds(self, toolbox, pop, nd_inds, num=None):

        if MPI_RANK != 0: return None

        if num == None: num = len(nd_inds)

        for i in range(num):
            if len(nd_inds) < 1: break
            
            i_nd = random.randint(0, len(nd_inds)-1)
            if nd_inds[i_nd] not in pop:
                i_p = random.randint(0, len(pop)-1)
                pop[i_p] = toolbox.clone(nd_inds[i_nd])
            del nd_inds[i_nd]

        return pop


    def replace_bad_inds(self, toolbox, pop, noninf_pop=None):

        if MPI_RANK != 0: return None

        for i in range(len(pop)):

            inf_val_checker = 1
            for j in range(self.problem_size):
                if pop[i].fitness.values[j] != self.inf_val:
                    inf_val_checker *= 0
            
            if inf_val_checker == 1:
                if noninf_pop == None:
                    del pop[i].fitness.values
                    pop[i] = toolbox.clone(toolbox.individual())
                else:
                    if len(noninf_pop) < 1: break
                    while len(noninf_pop) >= 1:
                        i_nd = random.randint(0, len(noninf_pop)-1)
                        if noninf_pop[i_nd] not in pop:
                            pop[i] = toolbox.clone(noninf_pop[i_nd])
                            del noninf_pop[i_nd]
                            break
                        else:
                            del noninf_pop[i_nd]              

        return pop


    def nsga2(self, fit_func, fit_func_args=[], init_pop=None):
        
        # init
        random.seed()
        self.fit_func = fit_func
        self.fit_func_args = fit_func_args
        toolbox = self.init_deap_functions()
        toolbox.register("select", tools.selNSGA2)

        if self.log_print: print("Number of used CPU: %i" % MPI_SIZE)

        # optimization
        result = self.optimize(toolbox, init_pop)
        
        if self.log_print: print("End of (successful) evolution")

        result_nd = self.get_nondominated_inds(toolbox, result)

        if self.log_file: 
            fh1 = open(self.log_file, 'a')
            fh1.write("\n-------------------------- End of (successful) evolution --------------------------\n")
            fh1.write("\nNon dominated individuals\n")
            for ind in result_nd:
                fh1.write("ind --> fit_func: " + str(ind) + ' --> ' + str(ind.fitness.values) + '\n')
            fh1.close()

        return result_nd


    def spea2(self, fit_func, fit_func_args=[], init_pop=None):
        
        # init
        random.seed()
        self.fit_func = fit_func
        self.fit_func_args = fit_func_args
        toolbox = self.init_deap_functions()
        toolbox.register("select", tools.selSPEA2)

        if self.log_print: print("Number of used CPU: %i" % MPI_SIZE)

        # optimization
        result = self.optimize(toolbox, init_pop)
        
        if self.log_print: print("End of (successful) evolution")

        result_nd = self.get_nondominated_inds(toolbox, result)

        if self.log_file: 
            fh1 = open(self.log_file, 'a')
            fh1.write("\n-------------------------- End of (successful) evolution --------------------------\n")
            fh1.write("\nNon dominated individuals\n")
            for ind in result_nd:
                fh1.write("ind --> fit_func: " + str(ind) + ' --> ' + str(ind.fitness.values) + '\n')
            fh1.close()

        return result_nd        
        
        
    def rwga(self):
        pass


    def de(self):
        pass


    def simplex(self):
        pass

