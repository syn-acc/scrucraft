"""SURV-01: finite food, native recovery, built shelter and bounded threat response.

Setup supplies mature plants, four raw logs, a crafting table and a stone work
scaffold. It never supplies prepared food, healing, placed shelter blocks or a
completed industrial output. This is an isolated acceptance journey, not evidence
of a self-sufficient settlement or the real-world Founders Mill objective.
"""
import math
import time

from gameplay_cases import done, quantity, slot
from isolated_game_fixture import wait_for


def run_cases(fixture, stream):
    def ticks(count):
        start = stream.observe()['world_tick']
        wait_for(lambda: stream.observe()['world_tick'] >= start + count, timeout=max(15, count / 10))

    def food_recovery_shelter_and_threat():
        stream.stop()
        fixture.console('tp VerifyBuilder 0.5 64 0.5')
        fixture.console('effect clear VerifyBuilder')
        fixture.console('fill -9 64 -7 12 73 8 air')
        fixture.console('fill -9 63 -7 12 63 8 stone')
        ticks(2)
        # Removing prior workstation blocks may spill inventory; erase setup
        # residue only after block removal, before the measured scene is seeded.
        fixture.console('kill @e[type=minecraft:item]')
        fixture.console('kill @e[tag=scru_survival_threat]')
        fixture.console('clear VerifyBuilder')
        ticks(6)
        assert not any(row.get('count', 0) for row in stream.observe()['inventory'])
        assert stream.observe()['health'] > 0
        done(stream, stream.select_slot(0))
        crops = [[x, 64, z] for x in range(2, 6) for z in range(-1, 2)]
        for x, y, z in crops:
            fixture.console(f'setblock {x} {y-1} {z} farmland[moisture=7]')
            fixture.console(f'setblock {x} {y} {z} wheat[age=7]')
        fixture.console('setblock 5 64 3 crafting_table')
        fixture.console('fill -6 64 -2 -6 64 2 stone')
        fixture.console('give VerifyBuilder minecraft:oak_log 4')
        wait_for(lambda: quantity(stream, 'minecraft:oak_log') == 4)

        # Harvest exactly the mature plants; no fixture command creates their
        # wheat or seed drops. Navigation also performs actual item pickup.
        for x in range(2, 6):
            for z in range(-1, 2):
                # Approach from the harvested column at matching z. Diagonal
                # rays from the row center can hit the neighboring mature crop's
                # outline first, especially on the lower farmland surface.
                done(stream, stream.move_to(x-.5, 64, z+.5))
                done(stream, stream.dig(x, 64, z))
            for z in range(-1, 2):
                done(stream, stream.move_to(x+.5, 64, z+.5))
            wait_for(lambda x=x: quantity(stream, 'minecraft:wheat') == (x-1)*3,
                     description='natural crop drops collected')
        harvested = done(stream, stream.query_blocks(positions=crops))['blocks']
        assert all(row['block'] == 'minecraft:air' for row in harvested), harvested
        seeds_before = quantity(stream, 'minecraft:wheat_seeds')
        seed_entities = sum(e.get('stack', {}).get('count', 0) for e in stream.observe()['entities']
                            if e.get('stack', {}).get('item') == 'minecraft:wheat_seeds')
        recipe = stream.recipe('minecraft:bread')
        assert recipe.get('supported'), recipe
        done(stream, stream.craft('minecraft:bread', 4, target=[5, 64, 3]))
        wait_for(lambda: quantity(stream, 'minecraft:bread') == 4)
        assert quantity(stream, 'minecraft:wheat') == 0

        # Native hunger and generic damage are explicit challenge inputs, not
        # fabricated inventory/health state or a healing-effect command.
        if stream.observe()['food'] > 10:
            fixture.console('effect give VerifyBuilder hunger 10 255 true')
            try:
                wait_for(lambda: stream.observe()['food'] <= 10, timeout=12, description='native hunger challenge')
            finally:
                fixture.console('effect clear VerifyBuilder')
        ticks(2)
        food_before = stream.observe()['food']
        health_before = stream.observe()['health']
        damage = min(6, health_before / 2)
        assert damage > 0
        fixture.console(f'damage VerifyBuilder {damage:.4f} minecraft:generic')
        damaged = wait_for(lambda: stream.observe()['health'] if stream.observe()['health'] <= health_before - damage*.8 else None,
                          description='native damage reduces health')
        done(stream, stream.select_slot(slot(stream, 'minecraft:bread')))
        consumed = 0
        for _ in range(4):
            if stream.observe()['food'] >= 20:
                break
            before = quantity(stream, 'minecraft:bread')
            assert before > 0
            result = done(stream, stream.use_item())
            wait_for(lambda before=before: quantity(stream, 'minecraft:bread') == before-1)
            assert result['reason'] == 'use_finished', result
            consumed += 1
        assert consumed and stream.observe()['food'] >= 18
        recovered = wait_for(lambda: stream.observe()['health'] if stream.observe()['health'] >= health_before else None,
                             timeout=35, description='vanilla food-driven natural health recovery')
        assert recovered > damaged and quantity(stream, 'minecraft:bread') == 4-consumed

        # Sixteen planks come from the four declared logs. Build a two-high
        # five-wide wall and a supported roof over the retreat cell (13 blocks).
        done(stream, stream.craft('minecraft:oak_planks', 4))
        wait_for(lambda: quantity(stream, 'minecraft:oak_planks') == 16)
        assert quantity(stream, 'minecraft:oak_log') == 0
        done(stream, stream.move_to(-5.5, 65, .5))
        done(stream, stream.select_slot(slot(stream, 'minecraft:oak_planks')))
        placed = []
        for z in range(-2, 3):
            done(stream, stream.move_to(-5.5, 65, z+.5))
            for y in (64, 65):
                done(stream, stream.place(-3, y, z, 'up'))
                placed.append([-3, y, z])
        done(stream, stream.place(-3, 66, 0, 'up'))
        placed.append([-3, 66, 0])
        for x in (-4, -5):
            done(stream, stream.place(x, 66, 0, 'west'))
            placed.append([x, 66, 0])
        assert quantity(stream, 'minecraft:oak_planks') == 3
        shelter_blocks = done(stream, stream.query_blocks(positions=placed))['blocks']
        assert len(shelter_blocks) == 13 and all(row['block'] == 'minecraft:oak_planks' for row in shelter_blocks)

        threat = None
        try:
            # BetterDifficulty's enabled spawn_blocker rejects new monsters
            # within 32 blocks of shared spawn. Move only this disposable world's
            # spawn beyond that radius; keep the mod and native hostile AI active.
            fixture.console('setworldspawn 128 64 128')
            fixture.console('time set midnight')
            fixture.console('summon minecraft:zombie 3.5 64 -3.5 {PersistenceRequired:1b,Tags:["scru_survival_threat"]}')
            threat = wait_for(lambda: next((entity for entity in stream.observe()['entities']
                if entity['type'] == 'minecraft:zombie' and entity.get('hostile')), None),
                description='native active hostile observed')
            health_at_response = stream.observe()['health']
            # Exit the scaffold sideways before going beneath the lower roof.
            # The active zombie remains governed by native AI throughout the response.
            done(stream, stream.move_to(-5.5, 64, 3.5))
            done(stream, stream.move_to(-4.5, 64, .5))
            position = stream.observe()['position']
            assert math.dist(position, [-4.5, 64, .5]) < .6, position
            wait_for(lambda: stream.observe()['sheltered'], description='SDK-built roof blocks sky exposure')
            hidden = wait_for(lambda: next((entity for entity in stream.observe()['entities']
                if entity['id'] == threat['id'] and not entity['visible']), None),
                timeout=5, description='built wall blocks line of sight to the threat')
            assert stream.observe()['health'] >= health_at_response, (health_at_response, stream.observe()['health'])
            final_seeds = quantity(stream, 'minecraft:wheat_seeds')
            final_seed_entities = sum(e.get('stack', {}).get('count', 0) for e in stream.observe()['entities']
                                      if e.get('stack', {}).get('item') == 'minecraft:wheat_seeds')
            assert final_seeds + final_seed_entities == seeds_before + seed_entities
            stream.stop()
            return {'supplied': {'mature_wheat_plants': 12, 'raw_oak_logs': 4, 'crafting_table': 1,
                                 'stone_platform_and_work_scaffold': True},
                    'gathered': {'wheat': 12, 'native_seed_drop_total': seeds_before + seed_entities,
                                 'final_seeds_inventory': final_seeds, 'final_seeds_world': final_seed_entities},
                    'food': {'bread_crafted': 4, 'bread_consumed': consumed, 'bread_remaining': 4-consumed,
                             'food_before': food_before, 'food_after': stream.observe()['food']},
                    'native_health': {'before_damage': health_before, 'challenge_damage': damage,
                                      'after_damage': damaged, 'after_food_recovery': recovered, 'healing_effects_injected': False},
                    'shelter': {'logs_consumed': 4, 'planks_crafted': 16, 'planks_placed': 13, 'planks_remaining': 3,
                                'roof_blocks_sky': True, 'placed_block_count_verified': len(shelter_blocks)},
                    'threat': {'type': threat['type'], 'hostile': threat['hostile'], 'native_ai_enabled': True,
                               'shared_spawn_during_threat': [128, 64, 128],
                               'betterdifficulty_spawn_blocker_preserved': True,
                               'response': 'finite SDK retreat behind built wall and beneath built roof',
                               'final_line_of_sight': hidden['visible'], 'response_health_preserved': True},
                    'prepared_food_or_heal_outputs_seeded': False, 'sustained_autonomy_or_founders_mill_claimed': False}
        finally:
            fixture.console('kill @e[tag=scru_survival_threat]')
            fixture.console('setworldspawn 0 64 0')
            fixture.console('time set day')
            stream.stop()

    fixture.case('survival_native_harvest_food_recovery_shelter_and_threat_response',
                 ['ACT-07', 'ACT-08', 'ACT-09', 'ACT-15', 'OBS-02', 'OBS-03', 'VERIFY-02', 'VERIFY-03', 'SURV-01'],
                 food_recovery_shelter_and_threat)
