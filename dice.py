import random


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
        return self.is_axe() and len([_ for _ in self.result_history if _ == 6]) == 1

    def explode(self):
        if self.can_explode():
            self.roll()



class DicePool():
    def __init__(self, num_dice=0):
        self.pool = [Die() for _ in range(num_dice)]
        self.result_history = []


    def size(self):
        return len(self.pool)


    def add_dice(self, n):
        self.pool = [Die() for _ in range(n)]


    def add_die(self):
        self.add_dice(1)


    def roll(self):
        for die in self.pool:
            die.roll()
        self.result_history.append([_.face() for _ in self.pool])


    def can_explode(self):
        for die in self.pool:
            if die.can_explode():
                return True
        return False


    def explode(self):
        for die in self.pool:
            die.explode()
        self.result_history.append([_.face() for _ in self.pool])


    def can_reroll(self):
        for die in self.pool:
            if die.can_reroll():
                return True
        return False


    def reroll_one(self):
        for die in self.pool:
            if die.can_reroll():
                die.roll()
                self.result_history.append([_.face() for _ in self.pool])
                return


    def reroll_all(self):
        for die in self.pool:
            if die.can_reroll():
                die.roll()
        self.result_history.append([_.face() for _ in self.pool])


    def num_successes(self):
        return sum([_.value() for _ in self.pool])


    def current_result(self):
        return self.result_history[-1] if self.result_history else []


    def num_axes(self):
        return len([_ for _ in self.pool if _.is_axe()]) if self.pool else 0


    def num_can_reroll(self):
        return len([_ for _ in self.pool if _.can_reroll()]) if self.pool else 0


    def num_can_explode(self):
        return len([_ for _ in self.pool if _.can_explode()]) if self.pool else 0

