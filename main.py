import sys
import json
from distutils.version import LooseVersion, StrictVersion
import re
import itertools
import pycosat

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

repoDict = {}


def build_packages_cnf(package):
    if 'cnf' not in package:
        package['cnf'] = []
        if 'depends' in package:
            for depends in package['depends']:
                sats = []
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

                    temp = []
                    try:
                        for val in repoDict[name]:
                            if does_match(val['version'], operator, version):
                                temp.append(val['id'])
                                build_packages_cnf(val)
                    except KeyError:
                        pass

                    sats.append(temp)

                mul = map(list, list(itertools.product(*sats)))
                package['cnf'].extend(mul)

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
                            package['cnf'].append([-val['id']])
                except KeyError:
                    pass

        package['cnf'].append([package['id']])


def main():
    for idx, package in enumerate(repoInput):
        package['id'] = idx + 1
        if package['name'] in repoDict:
            repoDict[package['name']].append(package)
        else:
            repoDict[package['name']] = [package]

    initial = []

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
                initial.append(val)
                found = True
                build_packages_cnf(val)
                break

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
                    tempPos.append(val['id'])
                    build_packages_cnf(val)
                else:
                    constraintsNegative.append([-val['id']])
                    build_packages_cnf(val)
                found = True

        constraintsPositive.append(tempPos)

        if not found:
            print(constraintIn)
            raise Exception("Constraint: not found")

    commands, cost = iterative_deepening(initial, 100000000000, len(repo)*2)
    commands.reverse()

    print(json.dumps(commands))


def iterative_deepening(state, max_cost, max_depth):
    seq = [x['size'] for x in repo]
    for i in (x*10 for x in range(100001, max_cost, round(4.01*min(seq)+50000))):
        commands, cost = depth_first(state, i, max_depth, [])
        if commands is not None:
            return commands, cost


def depth_first(state, max_cost, max_depth, visited_states):

    if state in visited_states:
        return None, 0

    if max_cost < 0:
        return None, 0

    if max_cost < 0:
        return None, 0

    if max_depth < 0:
        return None, 0

    cnf = build_cnf(state)

    if not is_valid(cnf):
        return None, 0

    if is_final(cnf):
        return [], 0

    visited_states.append(state)

    possibleAdd, possibleRemove = get_possible(state, visited_states)

    minCommands, minCost = None, 1000000000000

    for add in possibleAdd:
        tempState = state[:]
        tempState.append(add)
        commands, cost = depth_first(tempState, max_cost - add['size'], max_depth - 1, visited_states)
        if commands is not None and minCost > cost + add['size']:
            commands.append("+" + add['name'] + "=" + add['version'])
            minCommands, minCost = commands, cost + add['size']

    if max_cost - 1000000 > 0:
        for remove in possibleRemove:
            tempState = state[:]
            tempState.remove(remove)
            commands, cost = depth_first(tempState, max_cost - 1000000, max_depth - 1, visited_states)
            if commands is not None and minCost > cost + 1000000:
                commands.append("-" + remove['name'] + "=" + remove['version'])
                minCommands, minCost = commands, cost + 1000000

    return minCommands, minCost

counter = 0


def get_possible(state, visitedStates):

    possibleAdd = []
    possibleRemove = []
    for name, packages in repoDict.items():
        for package in packages:
            if 'cnf' in package:
                if package in state:
                    possibleRemove.append(package)
                else:
                    possibleAdd.append(package)

    return possibleAdd, possibleRemove


def build_cnf(state):
    cnf = []
    for key, packages in repoDict.items():
        for package in packages:
            if package in state:
                cnf.extend(package['cnf'])
            else:
                cnf.append([-package['id']])
    return cnf


def is_valid(cnf):
    return type(pycosat.solve(cnf)) is list


def is_final(cnf):
    cnf.extend(constraintsPositive)
    cnf.extend(constraintsNegative)
    return type(pycosat.solve(cnf)) is list


def does_match(version, operator, version2):
    if operator == "":
        return True

    return operators[operator](version, version2)


if __name__ == '__main__':
    main()
