import sys
import json
from packaging import version
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


matchString = r'(\w*)(\W*)([\w\.]*)'

operators = {
    "=": (lambda x, y: version.parse(x) == version.parse(y)),
    ">": (lambda x, y: version.parse(x) > version.parse(y)),
    ">=": (lambda x, y: version.parse(x) >= version.parse(y)),
    "<": (lambda x, y: version.parse(x) < version.parse(y)),
    "<=": (lambda x, y: version.parse(x) <= version.parse(y)),
}

constraintsPositive = []
constraintsNegative = []


def main():
    for packageIdx, package in enumerate(repoInput):
        repo[packageIdx]['cnf'] = []
        try:
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

                    for idx, val in enumerate(repoInput):
                        if does_match(val['name'], val['version'], operator, name, version):
                            temp.append(idx+1)

                    sats.append(temp)

                mul = map(list, list(itertools.product(*sats)))
                repo[packageIdx]['cnf'].extend(mul)
        except KeyError:
            pass

        try:
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

                for idx, val in enumerate(repoInput):
                    if does_match(val['name'], val['version'], operator, name, version):
                        repo[packageIdx]['cnf'].append([-(idx + 1)])
        except KeyError:
            pass

        repo[packageIdx]['cnf'].append([packageIdx+1])

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
        for val in repo:
            if does_match(val['name'], val['version'], operator, name, version):
                initial.append(val)
                found = True
                break

        if not found:
            raise Exception("Input: " + initialIn + " not found")


    for constraintIn in constraintsInput:

        matchObj = re.match(matchString, constraintIn[1:])
        if not matchObj:
            continue
        name = matchObj.group(1)
        operator = matchObj.group(2)
        version = matchObj.group(3)

        found = False
        for val in repo:
            if does_match(val['name'], val['version'], operator, name, version):
                if constraintIn[0] == '+':
                    constraintsPositive.append(val)
                else:
                    constraintsNegative.append(val)
                found = True
                break

        if not found:
            raise Exception("Constraint: " + constraintIn + " not found")

    commands, cost = iterative_deepening(initial, 100000)
    commands.reverse()
    print(json.dumps(commands))


def iterative_deepening(state, max_depth):
    for i in range(max_depth):
        commands, cost = depth_first(state, i)
        if commands is not None:
            return commands, cost


def depth_first(state, depth):
    if depth <= 0:
        return None, 0

    if is_final(state):
        return [], 0

    possibleAdd, possibleRemove = get_possible(state)


    for add in possibleAdd:
        tempState = state[:]
        tempState.append(add)
        commands, cost = depth_first(tempState, depth-1)
        if commands is not None:
            commands.append("+" + add['name'] + "=" + add['version'])
            return commands, cost + add['size']

    for remove in possibleRemove:
        tempState = state[:]
        tempState.remove(remove)
        commands, cost = depth_first(tempState, depth - 1)
        if commands is not None:
            commands.append("+" + remove['name'] + "=" + remove['version'])
            return commands, cost + 1000000

    return None, 0


def get_possible(state):
    possibleAdd = []
    possibleRemove = []
    for package in repo:
        temp = state[:]
        if package in state:
            temp.remove(package)
            if is_valid(temp):
                possibleRemove.append(package)
        else:
            temp.append(package)
            if is_valid(temp):
                possibleAdd.append(package)

    return possibleAdd, possibleRemove


def is_valid(state):
    cnf = []
    for idx, package in enumerate(repo):
        if package in state:
            cnf.extend(package['cnf'])
        else:
            cnf.append([-(idx+1)])
    return type(pycosat.solve(cnf)) is list


def is_final(state):
    return all(k in state for k in constraintsPositive) and all(k not in state for k in constraintsNegative)


def does_match(name, version, operator, name2, version2):
    if name != name2:
        return False

    if operator == "":
        return True

    return operators[operator](version, version2)


if __name__ == '__main__':
    main()
