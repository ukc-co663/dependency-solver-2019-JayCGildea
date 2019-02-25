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
                            temp.append(idx + 1)

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

        repo[packageIdx]['cnf'].append([packageIdx + 1])

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
        for idx, val in enumerate(repo):
            if does_match(val['name'], val['version'], operator, name, version):
                if constraintIn[0] == '+':
                    tempPos.append(idx + 1)
                else:
                    constraintsNegative.append([-(idx + 1)])
                found = True

        constraintsPositive.append(tempPos)

        if not found:
            print(constraintIn)
            raise Exception("Constraint: not found")

    commands, cost = iterative_deepening(initial, 1000000000, len(repo) * 10)
    commands.reverse()
    print(json.dumps(commands))


def iterative_deepening(state, max_cost, max_depth):
    for i in (10 ** x for x in range(0, max_cost)):
        commands, cost = depth_first(state, i, max_depth, [])
        if commands is not None:
            return commands, cost


def depth_first(state, max_cost, max_depth, visited_states):
    if max_cost < 0:
        return None, 0

    if max_depth < 0:
        return None, 0

    if is_final(state):
        return [], 0

    possibleAdd, possibleRemove = get_possible(state, visited_states)

    minCommands, minCost = None, 0

    for add in possibleAdd:
        tempState = state[:]
        tempState.append(add)
        commands, cost = depth_first(tempState, max_cost - add['size'], max_depth - 1, visited_states)
        if commands is not None and minCost < cost + add['size']:
            commands.append("+" + add['name'] + "=" + add['version'])
            minCommands, minCost = commands, cost + add['size']

    for remove in possibleRemove:
        tempState = state[:]
        tempState.remove(remove)
        commands, cost = depth_first(tempState, max_cost - 1000000, max_depth - 1, visited_states)
        if commands is not None and minCost < cost + 1000000:
            commands.append("+" + remove['name'] + "=" + remove['version'])
            minCommands, minCost = commands, cost + 1000000

    return minCommands, minCost


def get_possible(state, visitedStates):
    possibleAdd = []
    possibleRemove = []
    for package in repo:
        temp = state[:]
        if package in state:
            temp.remove(package)
            if is_valid(temp) and temp not in visitedStates:
                possibleRemove.append(package)
                visitedStates.append(temp)
        else:
            temp.append(package)
            if is_valid(temp) and temp not in visitedStates:
                possibleAdd.append(package)
                visitedStates.append(temp)

    return possibleAdd, possibleRemove


def build_cnf(state):
    cnf = []
    for idx, package in enumerate(repo):
        if package in state:
            cnf.extend(package['cnf'])
        else:
            cnf.append([-(idx + 1)])
    return cnf


def is_valid(state):
    cnf = build_cnf(state)
    return type(pycosat.solve(cnf)) is list


def is_final(state):
    cnf = build_cnf(state)
    cnf.extend(constraintsPositive)
    cnf.extend(constraintsNegative)
    return type(pycosat.solve(cnf)) is list


def does_match(name, version, operator, name2, version2):
    if name != name2:
        return False

    if operator == "":
        return True

    return operators[operator](version, version2)


if __name__ == '__main__':
    main()
