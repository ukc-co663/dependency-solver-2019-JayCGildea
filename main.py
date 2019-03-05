import sys
import json
from distutils.version import LooseVersion
import re
from queue import PriorityQueue
import itertools
import pycosat
import gc

with open(sys.argv[1], 'r') as f:
    repoInput = json.load(f)
    repo = repoInput[:]

with open(sys.argv[2], 'r') as f:
    initialInput = json.load(f)

with open(sys.argv[3], 'r') as f:
    constraintsInput = json.load(f)

matchString = r'([\w\.\+\-]*)(\W*)([\w\.]*)'

operators = {
    "=": (lambda x, y: LooseVersion(x) == LooseVersion(y)),
    ">": (lambda x, y: LooseVersion(x) > LooseVersion(y)),
    ">=": (lambda x, y: LooseVersion(x) >= LooseVersion(y)),
    "<": (lambda x, y: LooseVersion(x) < LooseVersion(y)),
    "<=": (lambda x, y: LooseVersion(x) <= LooseVersion(y)),
}

constraintsPositive = []
constraintsNegative = []

cnf = []
finalStates = []
initialState = set()

repoDict = {}
repoIdDict = {}
counter = 1


def build_packages_cnf(package):
    global counter
    if 'cnf' not in package:
        package['cnf'] = []
        package['id'] = counter
        counter += 1
        repoIdDict[package['id']] = package

        if 'depends' in package:
            for depends in package['depends']:
                temp = [-package['id']]
                for depend in depends:
                    # Loop over repo and enumerate every package that satisifies this depend
                    matchObj = re.match(matchString, depend)
                    if not matchObj:
                        continue
                    name = matchObj.group(1)
                    try:
                        operator = matchObj.group(2)
                        version = matchObj.group(3)
                    except IndexError:
                        operator = None
                        version = None

                    try:
                        for val in repoDict[name]:
                            if does_match(val['version'], operator, version):
                                build_packages_cnf(val)
                                temp.append(val['id'])

                    except KeyError:
                        pass

                cnf.append(temp)

        if 'conflicts' in package:
            for conflict in package['conflicts']:

                matchObj = re.match(matchString, conflict)
                if not matchObj:
                    continue
                name = matchObj.group(1)
                try:
                    operator = matchObj.group(2)
                    version = matchObj.group(3)
                except IndexError:
                    operator = None
                    version = None
                try:
                    for val in repoDict[name]:
                        if does_match(val['version'], operator, version):
                            build_packages_cnf(val)
                            cnf.append([-package['id'], -val['id']])

                except KeyError:
                    pass

        cnf.append([-package['id']])


def main():
    for idx, package in enumerate(repoInput):
        if package['name'] in repoDict:
            repoDict[package['name']].append(package)
        else:
            repoDict[package['name']] = [package]

    for initialIn in initialInput:
        matchObj = re.match(matchString, initialIn)
        if not matchObj:
            continue
        name = matchObj.group(1)
        try:
            operator = matchObj.group(2)
            version = matchObj.group(3)
        except IndexError:
            operator = None
            version = None

        found = False
        for val in repoDict[name]:

            if does_match(val['version'], operator, version):
                initialState.add(counter)
                build_packages_cnf(val)
                found = True

        if not found:
            print(initialIn)
            raise Exception("Input not found")

    for constraintIn in constraintsInput:

        matchObj = re.match(matchString, constraintIn[1:])
        if not matchObj:
            continue
        name = matchObj.group(1)
        operator = matchObj.group(2)
        version = matchObj.group(3)

        found = False
        tempPos = []
        for val in repoDict[name]:
            if does_match(val['version'], operator, version):
                if constraintIn[0] == '+':
                    build_packages_cnf(val)
                    tempPos.append(val['id'])
                else:
                    build_packages_cnf(val)
                    constraintsNegative.append(-val['id'])
                found = True
        if constraintIn[0] == '+':
            constraintsPositive.append(tempPos)

        if not found:
            print(constraintIn)
            raise Exception("Constraint: not found")

    posConstrains = map(list, list(itertools.product(*constraintsPositive)))

    for pos in posConstrains:
        pos.extend(constraintsNegative)
        finalStates.append(pos)

    commands = depth_first(frozenset(initialState))

    print(json.dumps(commands))

def depth_first(state):

    queue = PriorityQueue()
    queue.put((0, 1000-len([]), state, []))
    commands = []

    visited = dict()
    visited[state] = 0


    while not queue.empty():
        gc.collect()
        last_cost, length, current, commands = queue.get()

        if is_final(current):
            break

        transitions = get_possible(current)

        for transition in transitions:
            newState = set(current)
            if -transition in newState:
                newState.remove(-transition)
            else:
                newState.add(transition)

            newState = frozenset(newState)
            if not is_valid(newState):
                continue

            if transition > 0:
                new_cost = visited[current] + repoIdDict[transition]['size']
            else:
                new_cost = visited[current] + 1000000

            if newState not in visited or visited[newState] > new_cost:
                visited[newState] = new_cost
                prio = new_cost + get_difference(newState)
                newCommands = commands[:]
                name = repoIdDict[abs(transition)]['name'] + "=" + repoIdDict[abs(transition)]['version']
                newCommands.append("+" + name if transition > 0 else "-" + name)
                queue.put((prio, 1000-len(newCommands), newState, newCommands))

    return commands



def get_possible(state):

    transitions = []
    for id, package in repoIdDict.items():
        transitions.append(-id if id in state else id)

    return transitions


def build_cnf(state):
    tempCnf = cnf[:]

    for package in state:
        tempCnf.remove([-package])
        tempCnf.append([package])

    return tempCnf


def is_valid(state):
    return type(pycosat.solve(build_cnf(state))) is list


def get_difference(state):

    min_cost = 1000000000000000000

    for finalState in finalStates:
        cost = 0
        for p in finalState:
            if p > 0:
                if p not in state:
                    cost += repoIdDict[p]['size']
            else:
                if -p in state:
                    cost += 1000000
        if cost < min_cost:
            min_cost = cost

    return min_cost


def is_final(state):
    for finalState in finalStates:
        if is_final_inner(finalState, state):
            return True
    return False


def is_final_inner(finalState, state):
    for p in finalState:
        if p > 0:
            if p not in state:
                return False
        else:
            if -p in state:
                return False
    return True


def does_match(version, operator, version2):
    if operator == "":
        return True

    return operators[operator](version, version2)


if __name__ == '__main__':
    main()
