from enum import Enum
import random



class Operation(Enum):
    ROLL = 1
    REROLL = 2
    EXPLODE = 3


class Die():
    def __init__(self):
        self.result_history = []

    def roll(self):
        self.result_history.append(random.randint(1, 6))

    def value(self):
        return len([_ for _ in self.result_history if _ >= 4])

    def face(self):
        return self.result_history[-1] if self.result_history else 0

    def is_rolled(self):
        return len(self.result_history) > 0

    def is_snake(self):
        return self.is_rolled() and self.result_history[-1] <= 3

    def is_success(self):
        return self.is_rolled() and self.result_history[-1] >= 4

    def is_axe(self):
        return self.is_rolled() and self.result_history[-1] == 6        

    def can_reroll(self):
        return self.is_snake() and len(self.result_history) == 1

    def can_explode(self):
        return self.is_axe()

    def explode(self):
        if self.can_explode():
            self.roll()



class DicePool():
    def __init__(self, num_dice=0):
        self.dice = [Die() for _ in range(num_dice)]
        self.result_history = []
        self.change_history = []
        self.action_history = []

        # tuples (successes, value)
        self.value_history = []


    def size(self):
        return len(self.dice)


    def add_dice(self, n):
        self.dice += [Die() for _ in range(n)]


    def add_die(self):
        self.add_dice(1)


    def roll(self):
        for die in self.dice:
            die.roll()
        self.change_history.append([True for die in self.dice])
        self.result_history.append([die.face() for die in self.dice])
        self.value_history.append((self.num_successes(), self.value()))
        self.action_history.append(Operation.ROLL)


    def can_explode(self):
        for die in self.dice:
            if die.can_explode():
                return True
        return False


    def explode(self):
        self.change_history.append([die.can_explode() for die in self.dice])
        for die in self.dice:
            die.explode()
        self.result_history.append([die.face() for die in self.dice])
        self.value_history.append((self.num_successes(), self.value()))
        self.action_history.append(Operation.EXPLODE)


    def can_reroll(self):
        for die in self.dice:
            if die.can_reroll():
                return True
        return False


    def _reroll(self, n):
        change_state = []
        count = 0
        for die in self.dice:
            change_state.append(die.can_reroll())
            if die.can_reroll():
                die.roll()
                count += 1
                if count == n:
                    break

        self.change_history.append(change_state)
        self.result_history.append([die.face() for die in self.dice])
        self.value_history.append((self.num_successes(), self.value()))
        self.action_history.append(Operation.REROLL)


    def reroll_one(self):
        self._reroll(1)


    def reroll_all(self):
        self._reroll(self.num_snakes())


    def num_successes(self):
        return len([die for die in self.dice if die.is_success()])


    def value(self):
        return sum([die.value() for die in self.dice])


    def current_result(self):
        return self.result_history[-1] if self.result_history else []


    def num_axes(self):
        return len([die for die in self.dice if die.is_axe()]) if self.dice else 0


    def num_snakes(self):
        return self.size() - self.num_successes()


    def num_can_reroll(self):
        return len([die for die in self.dice if die.can_reroll()]) if self.dice else 0


    def num_can_explode(self):
        return len([die for die in self.dice if die.can_explode()]) if self.dice else 0


    def get_history(self):
        return [(
                    self.action_history[i],
                    self.result_history[i],
                    self.value_history[i][0],
                    self.value_history[i][1],
                    self.change_history[i]
                ) for i in range(len(self.action_history))]

